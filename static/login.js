const form = document.getElementById('loginForm');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('submit');
  const error = document.getElementById('error');
  button.disabled = true;
  error.textContent = '';
  try {
    const response = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: document.getElementById('username').value, password: document.getElementById('password').value,
                            remember: document.getElementById('remember').checked})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || I18n.t('Anmeldung fehlgeschlagen.'));
    window.location.replace('/');
  } catch (exception) {
    error.textContent = exception.message;
  } finally {
    button.disabled = false;
  }
});

fetch('/api/auth-status').then(r=>{if(!r.ok)throw new Error();return r.json()}).then(data=>{
  document.getElementById('username').hidden=data.needs_migration;
  document.getElementById('usernameLabel').hidden=data.needs_migration;
  document.getElementById('username').required=!data.needs_migration;
  document.getElementById('loginHint').textContent=data.needs_migration?I18n.t('Mit dem bisherigen App-Passwort anmelden. Danach unter Einstellungen das erste Benutzerkonto anlegen.'):'';
}).catch(()=>{document.getElementById('error').textContent=I18n.t('Anmeldeeinstellungen konnten nicht geladen werden. Bitte neu laden.')});
