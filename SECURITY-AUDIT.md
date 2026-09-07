# Security audit

Run on 2026-09-06 against the working tree. Everything ranked below has either
been fixed in this commit or is listed at the bottom as needing a decision.

Scope note on git history: this working copy has no commits in it, so there was
no local history to search. The findings below come from every file in the tree.
Nothing that looks like a credential turned up anywhere, so there is nothing to
rotate and nothing a history rewrite would need to remove. If you want the
published history checked too, that has to run against the GitHub clone.

## Ranked findings

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | Medium | No Content-Security-Policy on any page, so a single injected tag could load script from anywhere | Added a `default-src 'none'` policy to all three pages, with SHA-256 hashes for the inline scripts rather than `unsafe-inline` |
| 2 | Medium | `?when=` was interpolated straight into a `querySelector` in two places. `?when="` throws a SyntaxError out of `readUrl` and leaves the page blank | Compare `radio.value` instead of building a selector |
| 3 | Low/Medium | `event.url` is scraped from other people's sites and went onto an `href` unparsed, so a compromised source could ship `javascript:` | New `safeUrl()` parses the URL and only lets `http:` and `https:` through |
| 4 | Low | Scraper exception text was published verbatim into `events.json` and shown as a footer tooltip, including absolute runner paths | `scrub_error()` cuts paths to a bare filename and URLs to their host. Full traceback still goes to the Actions log |
| 5 | Low | `?event=__proto__` returned `Object.prototype`, which is truthy and is not an event | `hasOwnProperty` guard in `openShared` |
| 6 | Low | `tests.yml` declared no `permissions`, so it inherited whatever the repo default is | Pinned to `contents: read` |
| 7 | Low | Pillow is imported by `scripts/build_images.py` but was never declared, so whatever version happened to be installed got used | Added `Pillow>=10.4` to `requirements-dev.txt` |

## 1. Secrets and credentials

Nothing found. No API keys, tokens, passwords, connection strings or private
URLs in any source file, config file, workflow or build file. No `.env`, no
`.pem`, no `.key`, no `.netrc`. Scans for the usual token shapes (`ghp_`, `sk-`,
`AKIA`, `xox`, `AIza`, JWTs) came back empty.

Both workflows were read line by line. Neither takes a secret, and neither
echoes anything into the log that is not already public. `update-events.yml`
needs `contents: write` because it commits the day's data, and that is the
correct scope for it. The only credential in play is the automatic
`GITHUB_TOKEN`, which is scoped to the run and expires with it.

Nothing to rotate.

## 2. Dependencies

`pip-audit` and `npm audit` both ran with network access and both came back
clean.

| Package | Pinned as | Installed | Known CVEs |
|---------|-----------|-----------|------------|
| requests | `>=2.31` | 2.33.1 | none |
| beautifulsoup4 | `>=4.12` | 4.14.3 | none |
| PyYAML | `>=6.0` | 6.0.3 | none |
| pytest | `>=8.0` | 9.1.1 | none |
| jsdom | `^26.0.0` | 26.x | none |

Nothing unmaintained or deprecated. Every declared package is actually
imported. The one gap was the reverse: Pillow was imported without being
declared, now fixed.

The floors are lower bounds rather than pins, which is the right call for a
project with a daily unattended run, because a patched transitive dependency
gets picked up without you having to notice. The lockfile handles the JS side.

## 3. Input handling and injection

The paths named in the audit brief have moved since it was written. The site is
served from the repo root now, so it is `assets/app.js` and `assets/nlq.js`, and
the scraper config lives in `config/`, so it is `config/manual_events.yaml`.

**The DOM.** `app.js` uses `textContent` 56 times and `innerHTML` 3 times. All
three `innerHTML` writes are hardcoded string literals: a loading message, an
error message, and an icon constant followed by an empty `<span>` that gets
filled with `textContent`. No event data and no URL parameter reaches
`innerHTML` anywhere. That is the single most important thing in this section
and it was already right.

**Query parameters.** `readUrl` reads `q`, `date`, `tod`, `event`, `when` and
the filter names. `q` goes to `.value` on an input, which does not parse HTML.
The filter values land in a `Set` used for matching. `when` and `event` were the
two problems, findings 2 and 5 above, both fixed.

**The `?event=` deep link.** The id is used for a `state.byId` lookup and to
build an element id for `getElementById`. It never reaches HTML. The prototype
guard is finding 5.

**The search box (`nlq.js`).** The only `new RegExp` in the file is built from a
hardcoded weekday array, not from what someone typed, so there is no ReDoS path
from the search input. No DOM sinks in the file at all.

**Calendar deep links.** `googleLink` and `outlookLink` both build on a
hardcoded https origin and pass every value through `URLSearchParams`, so event
text is encoded properly on the way out. No change needed.

**The issue form template.** Nothing automated reads issues. You copy accepted
entries into `config/manual_events.yaml` by hand, which means there is no path
from a stranger's issue body into the repo without you reading it first. That is
the right design and it is worth keeping that way.

**YAML.** Every load in the project is `yaml.safe_load`. There is no
`yaml.load`, no `full_load`, no `unsafe_load`, and no custom `Loader=`. There is
now a test that walks the tree and fails if one appears.

**Path traversal.** The only place a scraped URL touches the filesystem is the
fetch cache in `http.py`, and the filename is
`sha1(url).hexdigest() + ".txt"`, which is hex only and cannot traverse. Feed
filenames come from a hardcoded list, and the stale-feed cleanup only ever
removes `.ics` files it found by listing its own output directory. No traversal
anywhere.

## 4. Headers, HTTPS and hosting

GitHub Pages will not set response headers, so the policy goes in a meta tag.
Added to `index.html`, `about.html` and `404.html`:

```
default-src 'none';
img-src 'self' data:;
font-src https://fonts.gstatic.com;
connect-src 'self';
manifest-src 'self';
base-uri 'none';
form-action 'self';
script-src 'self' <hashes on about.html>;
style-src 'self' https://fonts.googleapis.com <hash on 404.html>
```

No `unsafe-inline` and no `unsafe-eval` on either script or style. The inline
scripts on `about.html` and the inline style block on `404.html` are allowed by
SHA-256 hash instead. `base-uri 'none'` is worth calling out: without it, one
injected `<base>` tag repoints every relative script on the page.

This was verified in a real Chromium, not just in the test harness. The page
renders 11 cards, the filter panels open, the calendar menu builds all 33 items,
the `.ics` download still fires, Google Fonts still apply, and the theme toggle
on `about.html` still runs, all with zero CSP violations and zero JS errors. Five
hostile query strings were loaded as well, and all five now render normally.

Because the hashes will go stale the moment an inline script is edited, and
because a stale hash fails silently in the browser, there is a test that
recomputes them from the file and fails if they drift.

Other items in this section:

- Every external link already carries `rel="noopener"`. There is now a test
  that fails if one is added without it.
- No mixed content. Every asset, font and feed URL is https.
- No Subresource Integrity on the Google Fonts stylesheet, and that is correct
  rather than an oversight. Google serves different CSS to different browsers,
  so a pinned hash would break the fonts for some visitors. The CSP now
  restricts that stylesheet to `fonts.googleapis.com` and the font files to
  `fonts.gstatic.com`, which is the control that actually applies here.
- `webcal://` links are formed by swapping the scheme on an already-built https
  URL, so they inherit the correct host and path.
- No directory listing. `.nojekyll` is present and Pages does not list
  directories.
- `github.io` is on the HSTS preload list, so HTTPS is enforced by the browser
  before the first request. Worth confirming "Enforce HTTPS" is still ticked in
  the repo's Pages settings.
- `frame-ancestors`, `X-Content-Type-Options` and `Permissions-Policy` are
  ignored in a meta tag and can only be sent as real headers, which GitHub Pages
  cannot do. Getting them would mean putting something like Cloudflare in front
  of the site. For a public read-only calendar that is not worth it.

## 5. Debug artifacts and error leakage

One `console.error` in `app.js`, in the data-load failure handler, where it is
doing its job. No `console.log`, no `debugger`, no commented-out credentials, no
TODO or FIXME anywhere in the tree, no debug or verbose flag left switched on.

The scraper's stderr output is intentionally chatty, which is right, because
that stream only goes to the Actions log where you are the audience. The
important boundary is what crosses into `events.json` and gets published, and
that was finding 4. The footer tooltip now shows the exception type and a
cleaned message with paths and query strings taken out. The full traceback still
goes to stderr.

The Actions log itself prints source names and counts, and on failure an
exception plus traceback. Runner paths in there are the standard public
`/home/runner/work/...` shape, identical for every public repo, so there is
nothing sensitive in them.

## Needs your decision

Three things I did not change, because each is a real tradeoff rather than a
clear win.

**Pinning actions to commit SHAs.** `checkout@v4`, `setup-python@v5`,
`setup-node@v4` and `cache@v4` are pinned to major version tags. A tag can be
repointed by whoever owns the action, so the hardened version is to pin the full
40-character SHA. The cost is that Dependabot then has to bump them for you and
you have to merge those PRs. For a personal project pulling only first-party
GitHub actions, tags are a defensible place to stop. Say the word and I will
pin them.

**`npm install` to `npm ci` in `tests.yml`.** `npm ci` installs exactly what
`package-lock.json` says and fails if the two disagree, which is the behavior
you want in CI. It is a one-word change and I would recommend it, but it changes
how the job behaves so I left it to you.

**Enforce HTTPS in Pages settings.** Not something I can check or change from
here. Worth confirming it is ticked.

## Tests

343 Python and 133 JavaScript, all passing. The new ones are in
`tests/test_security.py` plus three added to `tests/frontend.test.mjs`. One of
them earned its keep immediately: the check for selectors built out of URL
parameters found a second instance of finding 2 that the first pass had missed.
