# Admin Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Elimină funcționalitățile placeholder nefolosite și înlocuiește butoanele email mock cu mailto: links funcționale; implementează gestiunea reală a utilizatorilor.

**Architecture:** Toate modificările sunt în `app.html` (fișier unic). Fără backend nou — userii se stochează în `State.users` + localStorage la fel ca articolele. Emailurile folosesc `mailto:` care deschide clientul email al adminului cu câmpuri pre-completate.

**Tech Stack:** Vanilla JS, HTML/CSS inline, localStorage, `mailto:` protocol

---

### Task 1: Elimină Ingest PDF din navigare

**Files:**
- Modify: `app.html` — ROLE_NAV, pageEditorIssues()

**Pasul 1:** În `ROLE_NAV` (linia ~3043), șterge linia cu `'ingest'` din array-ul `admin`:
```javascript
// ȘTERGE această linie din admin array:
{ icon:'solar:inbox-in-bold-duotone', label:'Ingest PDF', page:'ingest' },
```

**Pasul 2:** Tot în `ROLE_NAV`, șterge linia cu `'ingest'` din array-ul `editor`:
```javascript
// ȘTERGE această linie din editor array:
{ icon:'solar:inbox-in-bold-duotone', label:'Ingest PDF', page:'ingest', badge: '!' },
```

**Pasul 3:** În `pageEditorIssues()` (linia ~3384), înlocuiește headerul paginii:
```javascript
// ÎNAINTE:
return `
<div class="flex-between mb-24">
  <div>
    <div class="page-title">Numere publicate</div>
    <div class="page-subtitle">Gestionare numere și articole ale revistei.</div>
  </div>
  <button class="btn btn-primary" onclick="navigate('ingest')">📥 Ingest PDF nou</button>
</div>

// DUPĂ:
return `
<div class="mb-24">
  <div class="page-title">Numere publicate</div>
  <div class="page-subtitle">Gestionare numere și articole ale revistei.</div>
</div>
```

**Verificare:** Deschide app, login admin — sidebar nu mai are "Ingest PDF". Pagina Numere nu mai are butonul "Ingest PDF nou".

**Commit:**
```bash
git add app.html
git commit -m "admin: remove Ingest PDF from navigation and issues header"
```

---

### Task 2: Numere collapsible cu `<details>`

**Files:**
- Modify: `app.html` — `pageEditorIssues()`

**Context:** Fiecare card de număr are un `card-header` și un `card-body` cu tabelul de articole. Înlocuim card-ul cu un `<details>` nativ HTML — fără JS extra, accesibil, open/close din browser.

**Pasul 1:** Înlocuiește template-ul fiecărui card în `pageEditorIssues()`. Funcția curentă (linia ~3386) mapează `allIssuesSorted` și generează `<div class="card mb-16">...</div>`. Înlocuiește întregul template map cu:

```javascript
${allIssuesSorted.map(issue=>`
<details class="card mb-16" style="overflow:hidden;">
  <summary style="list-style:none;cursor:pointer;padding:20px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px;border-radius:inherit;">
    <div style="flex:1;">
      <span class="text-mono text-muted text-sm">Vol.${getIssueDisplayVolume(issue)} Nr.${issue.number} / ${issue.year} &nbsp;·&nbsp; ISSN ${JOURNAL.issn}</span>
      <div style="font-family:var(--font-serif);font-size:1.1rem;font-weight:700;margin-top:4px;">${issue.title}</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
      <span class="text-sm text-muted">${issue.article_count} art. &nbsp;·&nbsp; ${getIssueTotalPages(issue)} pag.</span>
      ${badgeStatus(issue.status)}
      <button class="btn btn-secondary btn-sm" onclick="event.preventDefault();navigate('public-issue',{id:'${issue.id}'})">Vizualizează</button>
    </div>
  </summary>
  <div style="border-top:1px solid var(--border);padding:0;">
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>
        <th style="background:var(--bg);padding:10px 16px;font-family:var(--font-mono);font-size:0.68rem;letter-spacing:0.09em;text-transform:uppercase;color:var(--text2);">Pagini</th>
        <th style="background:var(--bg);padding:10px 16px;font-family:var(--font-mono);font-size:0.68rem;letter-spacing:0.09em;text-transform:uppercase;color:var(--text2);">Titlu articol</th>
        <th style="background:var(--bg);padding:10px 16px;font-family:var(--font-mono);font-size:0.68rem;letter-spacing:0.09em;text-transform:uppercase;color:var(--text2);">Autori</th>
        <th style="background:var(--bg);padding:10px 16px;font-family:var(--font-mono);font-size:0.68rem;letter-spacing:0.09em;text-transform:uppercase;color:var(--text2);">Acțiuni</th>
      </tr></thead>
      <tbody>
      ${DB.getArticlesByIssue(issue.id).map(art=>`
        <tr>
          <td class="text-mono text-sm text-muted">${art.pages_start}–${art.pages_end}</td>
          <td><strong style="font-size:0.9rem;">${art.title}</strong></td>
          <td class="text-sm text-muted">${art.authors}</td>
          <td style="display:flex;gap:8px;">
            <button class="btn btn-secondary btn-sm" onclick="openAdminArticleEditor('${art.id}')">Editează</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('public-article',{id:'${art.id}'})">→</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>
  <div class="card-footer">
    <span class="text-sm text-muted">Publicat ${issue.date_published}</span>
  </div>
</details>`).join('')}`;
```

**Notă:** `event.preventDefault()` pe butonul Vizualizează previne toggle-ul `<details>` când dai click pe buton.

**Verificare:** Pagina "Numere" afișează carduri colapsate. Click pe titlu/header → se expandează lista articole. Click din nou → se colapsează.

**Commit:**
```bash
git add app.html
git commit -m "feat: make issues list collapsible with native <details> element"
```

---

### Task 3: Email comunicare reală via mailto:

**Files:**
- Modify: `app.html` — `sendDecision()`, `pageSubmissions()`, `pageSubmissionDetail()`

**Pasul 1:** Înlocuiește funcția `sendDecision()` (linia ~6642) cu versiunea care deschide clientul email:

```javascript
function sendDecision() {
  const sub = DB.getSubmission(State.pageParams?.id || '');
  if (!sub) { toast('Submisie negăsită.', 'error'); return; }
  const dec = document.getElementById('decision-select')?.value;
  if (!dec) { toast('Selectați o decizie!', 'error'); return; }
  const msg = document.getElementById('decision-msg')?.value || '';
  const decLabels = { accept: 'Acceptat', minor: 'Revizii minore', major: 'Revizii majore', reject: 'Respins' };
  const subject = encodeURIComponent(`Decizie editorială [${sub.id}] — ${decLabels[dec] || dec} — ${JOURNAL.abbr}`);
  const body = encodeURIComponent(msg);
  window.open(`mailto:${sub.email}?subject=${subject}&body=${body}`);
  toast('Client email deschis cu decizia pre-completată.', 'success');
}
```

**Pasul 2:** Adaugă funcția `deskRejectEmail(submissionId)` după `sendDecision()`:

```javascript
function deskRejectEmail(submissionId) {
  const sub = DB.getSubmission(String(submissionId || ''));
  if (!sub) return;
  const subject = encodeURIComponent(`Răspuns manuscris [${sub.id}] — ${JOURNAL.abbr}`);
  const body = encodeURIComponent(`Stimată/Stimate ${sub.authors},\n\nVă mulțumim pentru interesul acordat publicației noastre.\n\nDupă examinarea inițială a manuscrisului dumneavoastră „${sub.title}", am decis că acesta nu corespunde criteriilor editoriale actuale.\n\nVă dorim succes în demersurile viitoare,\nEchipa editorială ${JOURNAL.abbr}`);
  window.open(`mailto:${sub.email}?subject=${subject}&body=${body}`);
}
```

**Pasul 3:** Adaugă funcția `inviteReviewerEmail()`:

```javascript
function inviteReviewerEmail() {
  const sub = DB.getSubmission(State.pageParams?.id || '');
  if (!sub) return;
  const reviewerName = document.querySelector('#reviewer-select-name')?.value || 'Reviewer';
  const deadline = document.querySelector('#reviewer-deadline')?.value || '';
  const subject = encodeURIComponent(`Invitație peer review — ${sub.title} [${sub.id}] — ${JOURNAL.abbr}`);
  const body = encodeURIComponent(`Stimată/Stimate ${reviewerName},\n\nVă invităm să efectuați un peer review pentru manuscrisul:\n\n„${sub.title}"\nAutori: ${sub.authors}\n\nDeadline propus: ${deadline}\n\nVă rugăm să confirmați disponibilitatea.\n\nCu stimă,\nEchipa editorială ${JOURNAL.abbr}`);
  window.open(`mailto:?subject=${subject}&body=${body}`);
  toast('Client email deschis pentru invitație reviewer.', 'success');
}
```

**Pasul 4:** În `pageSubmissions()` (linia ~3806), înlocuiește butonul mock "✕ Respinge":

```javascript
// ÎNAINTE:
${s.status==='submitted'?`<button class="btn btn-danger btn-sm" onclick="toast('Respingere rapidă trimisă autorului','success')">✕ Respinge</button>`:''}

// DUPĂ:
${s.status==='submitted'?`<button class="btn btn-danger btn-sm" onclick="deskRejectEmail('${s.id}')">✕ Respinge</button>`:''}
```

De asemenea adaugă buton ✉ rapid pe fiecare rând:
```javascript
// Adaugă în tbl-actions, după butonul "Detalii →":
<button class="btn btn-secondary btn-sm" onclick="deskRejectEmail('${s.id}')" title="Email autor">✉</button>
```

**Pasul 5:** În `pageSubmissionDetail()` (linia ~3911), înlocuiește butonul "Trimite decizie":

```javascript
// ÎNAINTE:
<button class="btn btn-primary" onclick="sendDecision()">📧 Trimite decizie + email automat</button>

// DUPĂ:
<button class="btn btn-primary" onclick="sendDecision()">✉ Deschide email decizie</button>
```

**Pasul 6:** În `pageSubmissionDetail()` (linia ~3977), înlocuiește butonul "Invită reviewer":

Adaugă `id` pe selectul de reviewer și câmpul deadline, și înlocuiește butonul:

```javascript
// ÎNAINTE — select fără id:
<select>
  <option>Prof. Dr. Andreea Pop</option>
  ...

// DUPĂ — select cu id:
<select id="reviewer-select-name">
  <option>Prof. Dr. Andreea Pop</option>
  ...

// ÎNAINTE — deadline fără id:
<input type="date" value="2025-02-15">

// DUPĂ — deadline cu id:
<input type="date" id="reviewer-deadline" value="2025-02-15">

// ÎNAINTE — buton mock:
<button class="btn btn-primary w-full" onclick="toast('Invitație trimisă reviewerului!','success')">📧 Invită reviewer</button>

// DUPĂ — buton mailto::
<button class="btn btn-primary w-full" onclick="inviteReviewerEmail()">✉ Deschide email invitație reviewer</button>
```

**Pasul 7:** În `pageSubmissionDetail()` (linia ~3979), înlocuiește desk reject mock:

```javascript
// ÎNAINTE:
<button class="btn btn-danger btn-sm w-full" onclick="toast('Respingere rapidă trimisă autorului + email automat','success')">✕ Desk reject</button>

// DUPĂ:
<button class="btn btn-danger btn-sm w-full" onclick="deskRejectEmail('${s.id}')">✉ Desk reject (email)</button>
```

**Verificare:** Click "✉ Desk reject" → se deschide clientul email cu To:/Subject/Body pre-completate. Click "✉ Deschide email decizie" → același comportament.

**Commit:**
```bash
git add app.html
git commit -m "feat: replace mock email buttons with real mailto: links in submissions workflow"
```

---

### Task 4: Gestionare utilizatori funcțională (State + CRUD)

**Files:**
- Modify: `app.html` — State object, `pageAdminUsers()`, modal HTML, funcții CRUD

**Pasul 1:** Adaugă `users` în State object (linia ~2641, după `persistentAdminSavedAt`):

```javascript
// Adaugă în State = { ... }:
users: JSON.parse(localStorage.getItem('academcms-users-v1') || 'null') || [
  { id:'u1', name:'Admin System', email:'admin@iafar.ro', role:'Admin', status:'activ' },
  { id:'u2', name:'Elena Popescu', email:'e.popescu@iafar.ro', role:'Editor', status:'activ' },
  { id:'u3', name:'Ion Dumitrescu', email:'i.dumitrescu@ubb.ro', role:'Section Editor', status:'activ' },
  { id:'u4', name:'Prof. Dr. Andreea Pop', email:'a.pop@unibuc.ro', role:'Reviewer', status:'activ' },
  { id:'u5', name:'Prof. Dr. Mihai Lupu', email:'m.lupu@uvt.ro', role:'Reviewer', status:'activ' },
  { id:'u6', name:'Conf. Dr. Ioana Vasile', email:'i.vasile@uaic.ro', role:'Reviewer', status:'activ' },
],
```

**Pasul 2:** Adaugă funcția de persistență utilizatori (după `saveUserManifestOverride` sau grupat cu funcțiile de admin):

```javascript
function persistUsers() {
  try { localStorage.setItem('academcms-users-v1', JSON.stringify(State.users)); } catch(_) {}
}

function openUserModal(userId) {
  const user = userId ? State.users.find(u => u.id === userId) : null;
  const isNew = !user;
  document.getElementById('user-modal-title').textContent = isNew ? 'Utilizator nou' : 'Editează utilizator';
  document.getElementById('um-id').value = userId || ('u' + Date.now());
  document.getElementById('um-name').value = user?.name || '';
  document.getElementById('um-email').value = user?.email || '';
  document.getElementById('um-role').value = user?.role || 'Editor';
  document.getElementById('um-status').value = user?.status || 'activ';
  document.getElementById('user-modal').classList.remove('hidden');
}

function closeUserModal() {
  document.getElementById('user-modal').classList.add('hidden');
}

function saveUserModal() {
  const id = document.getElementById('um-id').value;
  const name = document.getElementById('um-name').value.trim();
  const email = document.getElementById('um-email').value.trim();
  const role = document.getElementById('um-role').value;
  const status = document.getElementById('um-status').value;
  if (!name || !email) { toast('Nume și email sunt obligatorii.', 'error'); return; }
  const existing = State.users.findIndex(u => u.id === id);
  if (existing >= 0) {
    State.users[existing] = { id, name, email, role, status };
  } else {
    State.users.push({ id, name, email, role, status });
  }
  persistUsers();
  closeUserModal();
  renderPage();
  toast('Utilizator salvat.', 'success');
}

function deleteUser(userId) {
  if (!confirm(`Șterge utilizatorul? Această acțiune nu poate fi anulată.`)) return;
  State.users = State.users.filter(u => u.id !== userId);
  persistUsers();
  renderPage();
  toast('Utilizator șters.', 'success');
}
```

**Pasul 3:** Înlocuiește `pageAdminUsers()` (linia ~5316) complet:

```javascript
function pageAdminUsers() {
  return `
<div class="flex-between mb-24">
  <div><div class="page-title">Utilizatori</div><div class="page-subtitle">Gestionare conturi și roluri.</div></div>
  <button class="btn btn-primary" onclick="openUserModal(null)">+ Utilizator nou</button>
</div>
<div class="tbl-wrap">
  <table>
    <thead><tr><th>Nume</th><th>Email</th><th>Rol</th><th>Status</th><th>Acțiuni</th></tr></thead>
    <tbody>
    ${State.users.map(u=>`
      <tr>
        <td><strong>${escapeHtml(u.name)}</strong></td>
        <td class="text-sm">${escapeHtml(u.email)}</td>
        <td><span class="badge badge-blue">${escapeHtml(u.role)}</span></td>
        <td><span class="badge ${u.status==='activ'?'badge-green':'badge-gray'}">${escapeHtml(u.status)}</span></td>
        <td class="tbl-actions">
          <button class="btn btn-secondary btn-sm" onclick="openUserModal('${u.id}')">Editează</button>
          ${u.role !== 'Admin' ? `<button class="btn btn-danger btn-sm" onclick="deleteUser('${u.id}')">Șterge</button>` : ''}
          <button class="btn btn-secondary btn-sm" onclick="window.open('mailto:${u.email}')">✉</button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table>
</div>`;
}
```

**Notă:** Utilizatorul cu rol `Admin` nu poate fi șters (protecție minimă).

**Pasul 4:** Adaugă HTML-ul pentru modalul de utilizator în `<body>`, după drawer-ul de articol (linia ~2070):

```html
<!-- USER EDIT MODAL -->
<div id="user-modal" class="modal-overlay hidden" onclick="if(event.target===this)closeUserModal()">
  <div class="modal" style="max-width:480px;">
    <div class="modal-header">
      <div class="modal-title" id="user-modal-title">Editează utilizator</div>
      <button class="btn-close" onclick="closeUserModal()">×</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="um-id">
      <div class="form-grid">
        <div class="form-field full">
          <label class="field-label">Nume complet <span class="field-req">*</span></label>
          <input type="text" id="um-name" placeholder="Prof. Dr. Nume Prenume">
        </div>
        <div class="form-field full">
          <label class="field-label">Email <span class="field-req">*</span></label>
          <input type="email" id="um-email" placeholder="email@institutie.ro">
        </div>
        <div class="form-field">
          <label class="field-label">Rol</label>
          <select id="um-role">
            <option value="Admin">Admin</option>
            <option value="Editor">Editor</option>
            <option value="Section Editor">Section Editor</option>
            <option value="Reviewer">Reviewer</option>
          </select>
        </div>
        <div class="form-field">
          <label class="field-label">Status</label>
          <select id="um-status">
            <option value="activ">Activ</option>
            <option value="inactiv">Inactiv</option>
          </select>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeUserModal()">Anulează</button>
      <button class="btn btn-primary" onclick="saveUserModal()">💾 Salvează</button>
    </div>
  </div>
</div>
```

**Verificare:**
- Pagina Utilizatori → buton "Editează" → modal cu date pre-completate → modifici → Salvează → lista se actualizează
- Buton "Șterge" → confirmare → utilizatorul dispare din listă
- Refresh pagină → utilizatorii editați persistă (localStorage)
- Utilizatorul Admin nu are buton Șterge

**Commit:**
```bash
git add app.html
git commit -m "feat: real user management with State persistence — add/edit/delete via modal"
```

---

### Task 5: Push final

```bash
git push origin main
```

**Verificare finală checklist:**
- [ ] Sidebar admin nu mai are "Ingest PDF"
- [ ] Pagina Numere: carduri se colapsează/expandează la click pe header
- [ ] Submissions: click "✕ Respinge" → se deschide clientul email
- [ ] Submission detail: click "✉ Deschide email decizie" → email pre-completat
- [ ] Submission detail: click "✉ Deschide email invitație reviewer" → email pre-completat
- [ ] Admin Utilizatori: Editează funcționează cu modal real
- [ ] Admin Utilizatori: Șterge funcționează cu confirmare
- [ ] Utilizatorii persistă după refresh
