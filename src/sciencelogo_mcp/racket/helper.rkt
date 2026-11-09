#lang racket/base
;; The server's Racket helper. It stays running and answers one JSON request
;; per line on standard input with one JSON reply per line on standard output.
;;
;;   {"id": 1, "op": "check", "entry": "/abs/workflow.rkt"}
;;   {"id": 1, "result": {...}}
;;   {"id": 1, "error": "..."}            the request itself failed
;;
;; Operations:
;;   check      read a workflow or library with the reference reader, without
;;              running it; for a valid workflow, also run the assessor
;;   structure  the items of a valid workflow, where each starts and ends, and
;;              a summary of its method
;;   translate  the verbose or compact text of a file, or of one span of it
;;   library    what a library provides: its procedures and record interfaces
;;   package    where the installed language package is, and its version

(require json
         racket/file
         racket/list
         racket/port
         racket/string
         sciencelogo/assessor
         sciencelogo/normalize
         sciencelogo/workflow-model
         (only-in sciencelogo/private/reader
                  parse-sciencelogo-file
                  parse-sciencelogo-tree-file
                  form-end
                  language-version
                  node->datum
                  node-kind
                  node-value
                  node-at
                  node-children
                  token?
                  token-line
                  token-column
                  token-position
                  token-source))

(provide check structure translate library)

(define (text v)
  (if v (format "~a" v) 'null))

;; --- check -----------------------------------------------------------------

(define (location e)
  (define where
    (and (exn:fail:read? e)
         (pair? (exn:fail:read-srclocs e))
         (car (exn:fail:read-srclocs e))))
  (define (field get)
    (define v (and where (get where)))
    (cond
      [(path? v) (path->string v)]
      [(or (string? v) (exact-integer? v)) v]
      [else 'null]))
  (hasheq 'file (field srcloc-source)
          'line (field srcloc-line)
          'column (field srcloc-column)))

;; The assessor's own report, and the outcome of each finding and check.
(define (assessment->jsexpr a)
  (hasheq 'report (with-output-to-string (lambda () (render-assessment a)))
          'findings (for/list ([f (in-list (assessment-findings a))])
                      (hasheq 'kind (text (finding-kind f))
                              'outcome (text (finding-outcome f))))
          'checks (for/list ([c (in-list (assessment-checks a))])
                    (text (condition-check-outcome c)))))

;; check : path-string string -> jsexpr
;; kind is "workflow" or "library".
(define (check entry [kind "workflow"])
  (with-handlers ([exn:fail?
                   (lambda (e)
                     (hash-set* (location e)
                                'status "invalid"
                                'message (exn-message e)))])
    (cond
      [(equal? kind "library")
       (parse-sciencelogo-file entry)
       (hasheq 'status "valid")]
      [else
       (define model (read-workflow-model entry))
       (hasheq 'status "valid"
               'assessment (assessment->jsexpr (assess-workflow model)))])))

;; --- structure ---------------------------------------------------------------

(define (point t)
  (if (token? t)
      (hasheq 'line (token-line t) 'column (token-column t) 'position (token-position t))
      'null))

(define (ref r)
  (if r
      (hasheq 'file (format "~a" (source-ref-source r))
              'line (source-ref-line r)
              'column (source-ref-column r)
              'position (source-ref-position r))
      'null))

(define (form-name form)
  (define v (node-value form))
  (case (node-kind form)
    [(stage interface phase performer resource must-call) (format "~a" v)]
    [(state-stage to) (format "~a" (car v))]
    [(proposition) (format "~a" (cadr v))]
    [(import) (format "~a" (list-ref v 3))]
    [(included-file) (format "~a" (car v))]
    [(must-stage-order) (string-join (map (lambda (x) (format "~a" x)) v) " ")]
    [else 'null]))

(define (form->jsexpr form)
  (define at (node-at form))
  (define base
    (hasheq 'kind (format "~a" (node-kind form))
            'name (form-name form)
            'file (if (token? at) (format "~a" (token-source at)) 'null)
            'start (point at)
            'end (point (form-end form))))
  (if (eq? (node-kind form) 'proposition)
      (hash-set base 'type (format "~a" (car (node-value form))))
      base))

(define (description d)
  (if d (description-model-text d) 'null))

(define (input-name id)
  (define m (regexp-match #rx"/input:([^/]*)$" id))
  (if m (cadr m) id))

;; structure : path-string string -> jsexpr
;; kind is "workflow" or "library". A library has items but no method summary.
(define (structure entry [kind "workflow"])
  (if (equal? kind "library")
      (library-structure entry)
      (workflow-structure entry)))

(define (library-structure entry)
  (hasheq 'title 'null
          'about 'null
          'items (map form->jsexpr (node-children (parse-sciencelogo-tree-file entry)))
          'stages '()
          'procedures '()
          'phases '()
          'performers '()
          'imports '()))

(define (workflow-structure entry)
  (define model (read-workflow-model entry))
  (define tree (parse-sciencelogo-tree-file entry))
  (define root (workflow-model-id model))
  (define names
    (make-immutable-hash
     (append (for/list ([s (workflow-model-stages model)])
               (cons (stage-model-id s) (format "~a" (stage-model-name s))))
             (for/list ([p (workflow-model-phases model)])
               (cons (phase-model-id p) (format "~a" (phase-model-name p)))))))
  (hasheq
   'title (text (workflow-model-title model))
   'about (description (workflow-model-description model))
   'items (map form->jsexpr (node-children tree))
   'stages (for/list ([s (workflow-model-stages model)])
             (hasheq 'name (format "~a" (stage-model-name s))
                     'about (description (stage-model-description s))
                     'performer (text (stage-model-performer s))
                     'in_procedure (not (equal? (stage-model-parent s) root))
                     'start (ref (stage-model-source s))
                     'end (ref (stage-model-end s))))
   'procedures (for/list ([p (workflow-model-procedures model)])
                 (hasheq 'name (format "~a" (procedure-model-name p))
                         'inputs (map input-name (procedure-model-inputs p))
                         'about (description (procedure-model-description p))
                         'start (ref (procedure-model-source p))
                         'end (ref (procedure-model-end p))))
   'phases (for/list ([p (workflow-model-phases model)])
             (hasheq 'name (format "~a" (phase-model-name p))
                     'about (description (phase-model-description p))
                     'members (for/list ([id (phase-model-members p)])
                                (hash-ref names id (lambda () (format "~a" id))))
                     'start (ref (phase-model-source p))
                     'end (ref (phase-model-end p))))
   'performers (for/list ([p (workflow-model-performers model)])
                 (format "~a" (performer-model-name p)))
   'imports (for/list ([i (workflow-model-imports model)])
              (hasheq 'alias (text (import-model-alias i))
                      'url (text (import-model-url i))
                      'version (text (import-model-requested-revision i))
                      'commit (text (import-model-commit i))
                      'language (text (import-model-language i))))))

;; --- translate -------------------------------------------------------------

;; translate : path-string string (or/c natural #f) (or/c natural #f) -> jsexpr
;; The text of `file` in the `to` syntax ("verbose" or "compact"). With start
;; and end positions of the source, only the text that comes from that span.
(define (translate file to [start #f] [end #f])
  (define result (translate-source (file->string file)
                                   #:to (string->symbol to)
                                   #:source (string->path file)))
  (define all (normalized-source-text result))
  (cond
    [(not start) (hasheq 'text all)]
    [else
     ;; Origins are one-based: character i has origin i + 1.
     (define (inside? i)
       (define origin (normalized-source-origin result (add1 i)))
       (and origin
            (equal? (format "~a" (source-origin-source origin)) file)
            (let ([p (source-origin-position origin)])
              (and p (>= p start) (or (not end) (< p end))))))
     (define hits (for/list ([i (in-range (string-length all))] #:when (inside? i)) i))
     (hasheq 'text (if (null? hits)
                       ""
                       (string-trim (substring all (first hits) (add1 (last hits)))
                                    #:left? #f)))]))

;; --- library ---------------------------------------------------------------

;; library : string string -> jsexpr
;; Reads a library through a workflow that only imports it, so the reader
;; fetches and checks it exactly as it would for a real import.
(define (library url version)
  (define dir (make-temporary-directory "sciencelogo-library-~a"))
  (dynamic-wind
   void
   (lambda ()
     (define entry (path->string (build-path dir "workflow.rkt")))
     (call-with-output-file entry
       (lambda (out)
         (fprintf out "#lang sciencelogo\nimport ~s at ~s as described\n" url version)))
     (define model (read-workflow-model entry))
     (define tree (parse-sciencelogo-tree-file entry))
     (define (local-name name)
       (define s (format "~a" name))
       (and (string-prefix? s "described.") (substring s 10)))
     (define import (car (workflow-model-imports model)))
     (hasheq
      'name (text (import-model-library-name import))
      'language (text (import-model-language import))
      'version (text (import-model-requested-revision import))
      'commit (text (import-model-commit import))
      'procedures
      (for/list ([p (workflow-model-procedures model)]
                 #:when (local-name (procedure-model-name p)))
        (hasheq 'name (local-name (procedure-model-name p))
                'inputs (map input-name (procedure-model-inputs p))
                'about (description (procedure-model-description p))))
      'interfaces
      (for/list ([form (node-children tree)]
                 #:when (and (eq? (node-kind form) 'interface)
                             (local-name (node-value form))))
        (hasheq 'name (local-name (node-value form))
                'fields (for/list ([entry (caddr (node->datum form))]
                                   #:when (and (pair? entry) (eq? (car entry) 'interface-field)))
                          (format "~a" (cadr entry)))))))
   (lambda () (delete-directory/files dir))))

;; --- protocol ----------------------------------------------------------------

(define (package)
  (hasheq 'dir (path->string (collection-file-path "main.rkt" "sciencelogo"))
          'version (text (language-version))))

(define (reply id key value)
  (write-json (hasheq 'id id key value))
  (newline)
  (flush-output))

(define (handle request)
  (define id (if (hash? request) (hash-ref request 'id 'null) 'null))
  (with-handlers ([exn:fail? (lambda (e) (reply id 'error (exn-message e)))])
    (unless (hash? request)
      (error 'helper "a request must be a JSON object"))
    (define op (hash-ref request 'op #f))
    (define (arg key [default #f])
      (define v (hash-ref request key default))
      (if (eq? v 'null) default v))
    ;; Anything the reference implementation prints must not reach the replies.
    (define result
      (parameterize ([current-output-port (open-output-nowhere)])
        (cond
          [(equal? op "check") (check (arg 'entry) (arg 'kind "workflow"))]
          [(equal? op "structure") (structure (arg 'entry) (arg 'kind "workflow"))]
          [(equal? op "translate") (translate (arg 'file) (arg 'to "verbose") (arg 'start) (arg 'end))]
          [(equal? op "library") (library (arg 'url) (arg 'version))]
          [(equal? op "package") (package)]
          [else (error 'helper "unknown operation: ~a" op)])))
    (reply id 'result result)))

(module+ main
  (let loop ()
    (define line (read-line (current-input-port) 'any))
    (unless (eof-object? line)
      (unless (string=? (string-trim line) "")
        (handle (with-handlers ([exn:fail? (lambda (e) #f)])
                  (string->jsexpr line))))
      (loop))))
