"""Build deployment-only copies from canonical source; never read local session data/secrets."""

from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
vendor = HERE / "src" / "vendor"
(vendor / "preprocessing_api").mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / "src/cogniflow_contracts", vendor / "cogniflow_contracts",
                dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
(vendor / "preprocessing_api/__init__.py").write_text("")
for name in ("schemas.py", "service.py"):
    shutil.copyfile(ROOT / "src/preprocessing_api" / name, vendor / "preprocessing_api" / name)
source = ROOT / "src/preprocessing_api/static/focus"
public = HERE / "public"
(public / "focus-assets").mkdir(parents=True, exist_ok=True)
for name in ("dashboard.css", "dashboard-state.js"):
    shutil.copyfile(source / name, public / "focus-assets" / name)
html = (source / "index.html").read_text()
for old, new in {
    "Local session data": "Private D1 session data",
    "Control a local focus session": "Control a private focus session",
    "Connect to your local CogniFlow API": "Sign in to your private workspace",
    "Local API key": "Owner login credential",
    'autocomplete="off"': 'autocomplete="current-password"',
    "Held in memory only. Refreshing requires\n            entering it again.": "A secure cookie keeps you signed in for up to eight hours. Sign out on shared devices.",
    "Connect locally": "Sign in",
    "Disconnect": "Sign out",
}.items():
    html = html.replace(old, new)
html = html.replace('<section class="timeline-section"', '''<section class="timeline-section" aria-labelledby="synthetic-title">
          <p class="kicker">Synthetic example only</p><h2 id="synthetic-title">demo_rule estimates</h2>
          <p>This fixed synthetic example is not a measurement of you. No trained model or camera is used.</p>
          <button id="synthetic-estimate" class="button secondary" type="button">Run synthetic demo_rule example</button>
          <p id="synthetic-result" role="status"></p>
        </section>
        <section class="timeline-section"''')
(public / "index.html").write_text(html)
js = (source / "dashboard.js").read_text()
js = js.replace("'X-API-Key': apiKey,", "'X-CogniFlow-CSRF': '1',")
js = js.replace("function disconnect() {", "function disconnect() {\n  fetch('/auth/logout', {method: 'POST', headers: {'Content-Type':'application/json', 'X-CogniFlow-CSRF':'1'}, body: '{}'}).catch(() => {});")
js = js.replace("apiKey = key; elements.credentialInput.value = ''; clearMessage();", """elements.credentialInput.value = ''; clearMessage();
  const login = await fetch('/auth/login', {method: 'POST', headers: {'Content-Type':'application/json', 'X-CogniFlow-CSRF':'1'}, body: JSON.stringify({credential:key})});
  if (!login.ok) throw new Error(userError(login.status, ''));
  apiKey = 'cookie';""")
js = js.replace("Re-enter the local API key.", "Sign in again.")
js = js.replace("Enter the local API key.", "Enter your owner login credential.")
js = js.replace("local CogniFlow service", "CogniFlow service").replace("local service", "service")
js = js.replace("Connected locally.", "Signed in securely.")
js = js.replace("if (status === 503)", "if (status === 429) return 'Too many requests. Wait a minute and try again.';\n  if (status === 503)")
# Restore cookie authentication through the existing session-recovery flow, without retaining the credential.
js += """
const syntheticButton = required('#synthetic-estimate', HTMLButtonElement);
syntheticButton.addEventListener('click', () => runBusy(syntheticButton, async () => {
  const result = await api('/predict', {method:'POST', body:JSON.stringify({focus_minutes:60, distraction_minutes:10, tasks_due:2, hours_to_deadline:24})});
  const history = await api('/estimates');
  required('#synthetic-result', HTMLElement).textContent = `${result.cognitive_load_level} · demo_rule · synthetic example. ${history.items.length} recent estimates saved.`;
}));
async function restoreCookie() {
  apiKey = 'cookie';
  try {
    await api('/sessions/auth-check');
    elements.credentialView.hidden = true; elements.appView.hidden = false;
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) await loadSession(stored);
  } catch { apiKey = null; elements.credentialView.hidden = false; elements.appView.hidden = true; }
}
restoreCookie();
"""
(public / "focus-assets/dashboard.js").write_text(js)
print("Prepared canonical contracts, rule calculation and dashboard (no session data).")
