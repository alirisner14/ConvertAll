# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

Until 1.0, only the latest minor release receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/alirisner14/ConvertAll/security/advisories/new)
(Security tab → Report a vulnerability). Include:

- what the problem is and what an attacker could do with it,
- the steps or a sample file that reproduces it,
- the ConvertAll, Python and OS versions you saw it on.

You can expect an acknowledgement within 72 hours and a status update within
seven days. If a fix is warranted, it ships in a patch release and you are
credited in the advisory unless you prefer otherwise.

## Threat model

ConvertAll is a local desktop application. It makes no network requests and
sends no telemetry. The realistic risk is **malicious input files**, since the
app parses untrusted images, audio, video and XML.

Mitigations in place:

- SVG parsing uses `lxml` with `resolve_entities=False`, which blocks XXE and
  billion-laughs entity-expansion attacks.
- Nothing in an input file is ever executed, and no `<script>` content is
  evaluated.
- FFmpeg is invoked with an argument list, never a shell string, so filenames
  cannot inject commands.
- Outputs are written to a chosen folder and never overwrite existing files.

Vulnerabilities in the upstream decoders themselves (Pillow, libwebp, FFmpeg,
lxml) should be reported to those projects; keep them updated with
`pip install -U -r requirements.txt`.
