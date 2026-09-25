# LTI 1.3 starter (pylti1p3 + Flask)

This is the piece that lets Canvas actually launch into a blend-zone tool.
Registering a Developer Key in Canvas
only tells Canvas the tool exists — this app is what Canvas talks to when
a student clicks the tool.

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Generate the signing keys**
   ```
   python generate_keys.py
   ```
   This creates `keys/private.pem` and `keys/public.pem`.

3. **Get this app reachable from the internet**
   Canvas needs to reach `/login`, `/launch`, and `/jwks` over HTTPS. For
   local testing, a tunnel tool (e.g. ngrok) works. For real use, this
   needs to run somewhere with a stable HTTPS URL — the Proxmox cluster,
   once it's reachable from outside the network, or any small hosted box.

4. **Register the Developer Key in Canvas** (see the earlier walkthrough)
   using this app's URLs:
   - **OpenID Connect Initiation URL:** `https://your-domain/login`
   - **Target Link URI:** `https://your-domain/launch`
   - **Public JWK URL:** `https://your-domain/jwks`

5. **Fill in `lti_config.json`** with the Client ID and Deployment ID
   Canvas gives you after the key is saved and activated.

6. **Run it**
   ```
   python app.py
   ```
   For anything beyond local testing, run it behind a real WSGI server
   (gunicorn) rather than Flask's dev server.

## What to change for the real tool

`/launch` currently just prints the student's name, role, and course —
replace that placeholder with a redirect (or server-side render) into the
actual blend-zone tool, passing along whatever identity/context it needs.

If you want roster pull or grade push, `message_launch.get_nrps()` and
`message_launch.get_ags()` inside `/launch` are where those calls go —
both require the matching service to be enabled on the Developer Key in
Canvas (Names and Role Provisioning / Assignment and Grade Services).

## A note on scope

This skeleton proves the handshake works — signed launch, verified
identity, roster/grade services available. It intentionally doesn't
include session management hardening, HTTPS enforcement, or production
error handling. Treat it as the starting point for a real implementation,
not a finished one.
