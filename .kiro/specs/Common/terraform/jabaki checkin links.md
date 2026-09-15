# Due to the migration of jabaki.nl from squarespace to aws domains
There seems to be missing the following forwarding links
- gscheckin.jabaki.nl  to  https://sites.google.com/pgeers.nl/jabaki/checkingreenstudio
- rscheckin.jabaki.nl  to  https://sites.google.com/pgeers.nl/jabaki/checkinredstudio
- gascheckin.jabaki.nl to  https://sites.google.com/pgeers.nl/jabaki/checkingardenstudio

Can we add this domain forwarding properly to the domain settings. And test if these work again

---

## Analysis & Recommended Approach

### Requested redirects

| Subdomain | Target |
|---|---|
| `gscheckin.jabaki.nl` | `https://sites.google.com/pgeers.nl/jabaki/checkingreenstudio` |
| `rscheckin.jabaki.nl` | `https://sites.google.com/pgeers.nl/jabaki/checkinredstudio` |
| `gascheckin.jabaki.nl` | `https://sites.google.com/pgeers.nl/jabaki/checkingardenstudio` |

### Why they broke

These previously worked because **Squarespace provided built-in subdomain forwarding**. That
was a Squarespace HTTP-redirect feature, not a DNS record. When `jabaki.nl` migrated to Route 53,
nothing in Terraform recreated them, so the forwarding was left behind.

### Why this is not a simple DNS record

DNS resolves a name to an address; it **cannot issue an HTTP redirect**. A "forward to an
`https://` URL" is a 301/302 redirect, which needs something serving HTTP to issue it.

There is also a trap in the current setup (`route53-jabaki.tf` + `landing-pages.tf`):

- The wildcard record `*.jabaki.nl` already points at the `public_pages` CloudFront distribution,
  so `gscheckin.jabaki.nl` (etc.) **already resolves** — it lands on CloudFront.
- The CloudFront function `public_pages_url_rewrite` treats any `*.jabaki.nl` host as a landing-page
  slug and rewrites the request to `/gscheckin/index.html` in S3. That object does not exist, so the
  visitor gets the **404 page** instead of a redirect.

So these hosts are not "missing DNS" — they are being swallowed by the wildcard and 404'ing.

### Recommended fix — redirect inside the existing CloudFront function

Handle the redirect inside the CloudFront function that already exists
(`aws_cloudfront_function.public_pages_url_rewrite` in `infrastructure/landing-pages.tf`), keyed on
the specific hostnames, **before** the generic slug logic runs.

- No new CloudFront distribution.
- No new ACM certificate (the `*.jabaki.nl` wildcard cert already covers these hosts).
- No new DNS records (the wildcard already resolves them).

Add this at the top of the `handler`, right after `host` is read and before the
`host.endsWith('.jabaki.nl')` block:

```js
// --- Static subdomain redirects (Squarespace migration) ---
var redirects = {
  'gscheckin.jabaki.nl':  'https://sites.google.com/pgeers.nl/jabaki/checkingreenstudio',
  'rscheckin.jabaki.nl':  'https://sites.google.com/pgeers.nl/jabaki/checkinredstudio',
  'gascheckin.jabaki.nl': 'https://sites.google.com/pgeers.nl/jabaki/checkingardenstudio',
};
if (redirects[host]) {
  return {
    statusCode: 302,
    statusDescription: 'Found',
    headers: { location: { value: redirects[host] } },
  };
}
```

Then `terraform apply` to republish the function.

Notes:
- Use **302** while testing (avoids browsers caching a bad redirect); switch to **301** once
  confirmed if you want it permanent.
- **Verify the exact Google Sites paths first** — `checkingreenstudio` / `checkingardenstudio`
  are easy to mistype (`checkin` + `green` / `garden`). Confirm each target URL actually loads
  before wiring it up.

### Alternatives considered (not recommended)

- **S3 redirect objects** (`gscheckin/index.html` with S3 website redirect metadata): the bucket is
  served via CloudFront OAC (S3 REST endpoint), not the S3 website endpoint, so S3 redirect headers
  would not be honored. More rework than the function approach.
- **Dedicated CloudFront distribution per host**: overkill for three static redirects.

### Testing

After apply:

```bash
for h in gscheckin rscheckin gascheckin; do
  echo "=== $h.jabaki.nl ==="
  curl -sI "https://$h.jabaki.nl" | grep -iE "^HTTP|^location"
done
```

Expect a `302` (or `301`) and a `location:` header pointing at the correct Google Sites URL for
each host.

### Recommendation

Go with the CloudFront-function redirect: smallest change, reuses the wildcard DNS and wildcard
cert already in place, and stays in Terraform so it survives future rebuilds.
