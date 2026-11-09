#lang racket/base
;; The server's Racket helper. It stays running and answers one JSON request
;; per line on standard input with one JSON reply per line on standard output.
;;
;;   {"id": 1, "op": "check", "entry": "/abs/workflow.rkt"}
;;   {"id": 1, "result": {"status": "valid"}}
;;   {"id": 1, "result": {"status": "invalid", "message": "...",
;;                        "file": "...", "line": 3, "column": 0}}
;;   {"id": 1, "error": "..."}            the request itself failed

(require json
         racket/port
         racket/string
         sciencelogo/workflow-model)

(provide check)

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

;; check : path-string -> jsexpr
;; Reads the workflow with the reference reader, without running it.
(define (check entry)
  (with-handlers ([exn:fail?
                   (lambda (e)
                     (hash-set* (location e)
                                'status "invalid"
                                'message (exn-message e)))])
    (read-workflow-model entry)
    (hasheq 'status "valid")))

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
    ;; Anything the reference implementation prints must not reach the replies.
    (define result
      (parameterize ([current-output-port (open-output-nowhere)])
        (cond
          [(equal? op "check") (check (hash-ref request 'entry))]
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
