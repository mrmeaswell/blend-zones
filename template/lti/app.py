"""
Minimal LTI 1.3 tool provider using pylti1p3 + Flask.

This is the piece Canvas actually talks to. Register a Developer Key in
Canvas pointing at this app's /login, /launch, and /jwks routes (see the
README in this folder), and Canvas will launch students straight from a
course page into whatever /launch hands off to.

Get this running locally first (it works over plain HTTP on localhost for
testing with a tool like ngrok), then move it wherever the real tool ends
up hosted — Proxmox, wherever.
"""

import os
import json
from flask import Flask, request, redirect, render_template_string
from flask_caching import Cache
from pylti1p3.contrib.flask import (
    FlaskOIDCLogin,
    FlaskMessageLaunch,
    FlaskRequest,
    FlaskCacheDataStorage,
)
from pylti1p3.tool_config import ToolConfJsonFile

app = Flask(__name__)

# CHANGE THIS to a real random secret before deploying anywhere real.
app.secret_key = os.environ.get("BZ_SECRET_KEY", "replace-me-with-a-random-secret-key")
app.config["CACHE_TYPE"] = "SimpleCache"
cache = Cache(app)

TOOL_CONF_FILE = "lti_config.json"


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Step 1 of the LTI launch: Canvas redirects the browser here first
    (the OpenID Connect Initiation URL you register in Canvas).
    """
    tool_conf = ToolConfJsonFile(TOOL_CONF_FILE)
    flask_request = FlaskRequest()
    target_link_uri = flask_request.get_param("target_link_uri")
    if not target_link_uri:
        return 'Missing "target_link_uri" param', 400

    oidc_login = FlaskOIDCLogin(
        flask_request, tool_conf, launch_data_storage=get_launch_data_storage()
    )
    return oidc_login.enable_check_cookies().redirect(target_link_uri)


@app.route("/launch", methods=["POST"])
def launch():
    """
    Step 2: Canvas POSTs a signed JWT here (the Target Link URI). This
    validates it and gives you the student's identity, course context,
    and role — this is where you'd hand off into the real tool.
    """
    tool_conf = ToolConfJsonFile(TOOL_CONF_FILE)
    flask_request = FlaskRequest()
    message_launch = FlaskMessageLaunch(
        flask_request, tool_conf, launch_data_storage=get_launch_data_storage()
    )
    launch_data = message_launch.get_launch_data()

    name = launch_data.get("name", "unknown user")
    roles = launch_data.get(
        "https://purl.imsglobal.org/spec/lti/claim/roles", []
    )
    context = launch_data.get(
        "https://purl.imsglobal.org/spec/lti/claim/context", {}
    )

    # --- Placeholder hand-off ---
    # Replace this with a redirect into the real tool (e.g. Bay Log),
    # passing along whatever identity/context it needs. If you're doing
    # roster pull or grade push, this is also where you'd call:
    #   message_launch.get_nrps()  -> Names and Role Provisioning (roster)
    #   message_launch.get_ags()   -> Assignment and Grade Services (grades)
    return render_template_string(
        """
        <h1>LTI launch received</h1>
        <p><strong>User:</strong> {{ name }}</p>
        <p><strong>Roles:</strong> {{ roles }}</p>
        <p><strong>Course:</strong> {{ context }}</p>
        <p>Replace this page with a redirect into the actual tool.</p>
        """,
        name=name,
        roles=roles,
        context=context.get("title", "unknown course"),
    )


@app.route("/jwks", methods=["GET"])
def jwks():
    """
    Canvas fetches this to verify your tool's identity. Point the
    Developer Key's "Public JWK URL" field at this route.
    """
    tool_conf = ToolConfJsonFile(TOOL_CONF_FILE)
    return json.dumps(tool_conf.get_jwks())


if __name__ == "__main__":
    app.run(debug=True, port=5000)
