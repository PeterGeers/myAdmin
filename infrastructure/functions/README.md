# CloudFront Function tests (`infrastructure/functions/`)

Committed unit tests for the inline CloudFront Functions defined in the
`infrastructure/*.tf` files. These functions run JS at the CDN edge
(`cloudfront-js-2.0`) and are defined inline in Terraform heredocs
(`code = <<-EOF ... EOF`) because a CloudFront Function must be a single
self-contained source — there is no separate `.js` deploy artifact to import.

To test that edge logic WITHOUT deploying, the harness reads the `.tf`, extracts
the EXACT heredoc body for a named function, and evaluates it against a mocked
`cloudfront` runtime module. The deployed source is the single source of truth —
the test never keeps a second, drift-prone copy of the handler.

## Files

| File | Purpose |
| --- | --- |
| `extract-tf-function.mjs` | Reads a `.tf` file, extracts a named `aws_cloudfront_function`'s `code` heredoc, and loads it as a callable `handler` with `cf` injected. |
| `application-form-frame-ancestors.test.mjs` | Tests the `application_form_frame_ancestors` viewer-response function (CSP `frame-ancestors` from `application_embed_origins`). Spec Members/11 task 5.2/5.4, R5.2. |

## Running

Node's built-in test runner (Node >= 18) — no dependencies, no new toolchain.
Use the `*.test.mjs` glob (the helper `extract-tf-function.mjs` is NOT a test file,
so a bare-directory arg would try to load it; the glob only discovers test files):

```bash
# all CloudFront-function tests
cd /home/peter/projects/myAdmin && node --test 'infrastructure/functions/*.test.mjs'

# a single file
cd /home/peter/projects/myAdmin && node --test infrastructure/functions/application-form-frame-ancestors.test.mjs
```

## What the frame-ancestors test asserts (R5.2)

| Scenario | Expected |
| --- | --- |
| Configured host, one/many origins | `content-security-policy: frame-ancestors <origins>` set |
| Extra whitespace in the KVS value | directive whitespace-collapsed |
| Unconfigured host (no KVS key) | NO header (standalone, not embeddable) |
| Empty / whitespace-only KVS value | NO header |
| KVS lookup error | NO header (fail-closed) |
| Missing host header | NO header |
| KVS binding unavailable | NO header (fail-closed) |

Standalone = no `frame-ancestors` header emitted, equivalent to `frame-ancestors 'none'`
(the browser blocks embedding), per `application-form.tf` and design §10.
