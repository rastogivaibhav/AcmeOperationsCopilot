'use strict';
// W08: role-aware, owner-scoped website. Text is never interpolated into HTML.
const root = document.getElementById('workspace');
const csrf = root.dataset.csrf;
const list = document.getElementById('conversations');
const error = document.getElementById('error');
const chatMessages = document.getElementById('chat-messages');
const chatTitle = document.getElementById('chat-title');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const evidence = document.getElementById('chat-evidence');
let selectedConversationId = null;
let busy = false;

function showError(message) { error.textContent = message; error.hidden = false; }
function clearError() { error.textContent = ''; error.hidden = true; }
function element(tag, text, className) {
  const item = document.createElement(tag);
  item.textContent = text;
  if (className) item.className = className;
  return item;
}
function setBusy(state) {
  busy = state;
  chatInput.disabled = !selectedConversationId || state;
  chatSend.disabled = !selectedConversationId || state;
  chatSend.textContent = state ? 'Agent is investigating…' : 'Send to agent';
}
function renderBubble(role, content) {
  const item = element('div', '', 'chat-bubble ' + role);
  item.append(element('small', role === 'user' ? 'You' : role === 'assistant' ? 'Agent' : 'System'));
  item.append(element('div', content));
  chatMessages.append(item);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
async function openConversation(id) {
  if (busy) return;
  clearError();
  try {
    const response = await fetch('/api/conversations/' + encodeURIComponent(id), {
      credentials:'same-origin'
    });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (!response.ok) throw new Error('Unable to open investigation (' + response.status + ')');
    const item = await response.json();
    selectedConversationId = item.id;
    chatTitle.textContent = item.title;
    chatMessages.replaceChildren();
    for (const msg of item.messages) renderBubble(msg.role, msg.body);
    if (!item.messages.length) chatMessages.append(element('p', 'Ask the agent a question to begin.', 'muted'));
    evidence.textContent = '';
    setBusy(false);
    window.history.replaceState(null, '', '/app?conversation=' + encodeURIComponent(item.id));
    for (const link of list.querySelectorAll('a')) {
      link.classList.toggle('active', link.dataset.conversationId === item.id);
    }
  } catch (e) { showError(e.message); }
}
async function loadConversations() {
  clearError();
  try {
    const response = await fetch('/api/conversations', {credentials:'same-origin'});
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (!response.ok) throw new Error('Cannot load investigations');
    const result = await response.json();
    list.replaceChildren();
    if (!result.items.length) {
      list.append(element('p', 'No investigations yet. Create one to get started.', 'muted'));
      return;
    }
    for (const item of result.items) {
      const link = element('a', '', 'conversation-entry');
      link.href = '/app?conversation=' + encodeURIComponent(item.id);
      link.dataset.conversationId = item.id;
      link.append(element('strong', item.title));
      link.append(element('small', 'Updated ' + new Date(item.updated_at).toLocaleString()));
      link.addEventListener('click', e => { e.preventDefault(); openConversation(item.id); });
      if (item.id === selectedConversationId) link.classList.add('active');
      list.append(link);
    }
  } catch (e) { showError(e.message); }
}
document.getElementById('new-conversation').addEventListener('submit', async (e) => {
  e.preventDefault(); clearError();
  try {
    const title = document.getElementById('title').value.trim();
    const response = await fetch('/api/conversations', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({title})
    });
    if (!response.ok) throw new Error('Unable to create investigation (' + response.status + ')');
    const created = await response.json();
    document.getElementById('title').value = '';
    await loadConversations();
    await openConversation(created.id);
  } catch (e) { showError(e.message); }
});
document.getElementById('chat-form').addEventListener('submit', async e => {
  e.preventDefault(); clearError();
  if (!selectedConversationId || busy) return;
  const message = chatInput.value.trim();
  if (!message || message.length > 2000) return;
  setBusy(true);
  evidence.textContent = '';
  try {
    const response = await fetch('/api/conversations/' + encodeURIComponent(selectedConversationId) + '/messages', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({message})
    });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (!response.ok) throw new Error('Agent execution failed (' + response.status + '). Check Docker logs.');
    const result = await response.json();
    renderBubble('user', message);
    renderBubble(result.status === 'complete' ? 'assistant' : 'system_notice', result.answer);
    chatInput.value = '';
    if (Array.isArray(result.proposed_actions) && result.proposed_actions.length) {
      const proposal = result.proposed_actions[result.proposed_actions.length - 1];
      fillActionForm(proposal);
      evidence.textContent = 'Agent proposed an action. Review it in the Controlled Action Centre; nothing has been committed.';
    }
    const refs = Array.isArray(result.evidence_refs) ? result.evidence_refs.join(', ') : '';
    const tools = Array.isArray(result.tool_events) ? result.tool_events.map(t => t.name + ': ' + t.status).join(' | ') : '';
    evidence.textContent = 'Evidence: ' + (refs || 'None returned') + '\nTools: ' + (tools || 'No tools invoked');
    await loadConversations();
    await loadActivity();
  } catch (e) { showError(e.message); }
  finally { setBusy(false); }
});
document.getElementById('logout').addEventListener('click', async () => {
  try {
    const response = await fetch('/logout', {
      method:'POST', credentials:'same-origin',
      headers:{'X-CSRF-Token':csrf, 'Accept':'application/json'}
    });
    if (response.status === 401) { window.location.href = '/'; return; }
    if (!response.ok) throw new Error('Sign-out failed');
    const {logout_url} = await response.json();
    window.location.assign(logout_url);
  } catch (e) { showError('Sign-out failed; please retry.'); }
});
(async function initialize() {
  await loadConversations();
  const requested = new URLSearchParams(window.location.search).get('conversation');
  if (requested && /^[0-9a-f-]{36}$/i.test(requested)) await openConversation(requested);
})();

// W10 browser confirmation: the model never receives approval IDs or operation IDs.
const actionForm = document.getElementById('action-prepare-form');
const actionKind = document.getElementById('action-kind');
const confirmationPanel = document.getElementById('action-confirm-panel');
let pendingApprovalId = null;
function fillActionForm(proposal) {
  if (!actionForm || !proposal || !['issue_update','next_action'].includes(proposal.kind)) return;
  if (!Array.from(actionKind.options).some(o => o.value === proposal.kind)) return;
  actionKind.value = proposal.kind;
  document.getElementById('action-issue-id').value = proposal.issue_id || '';
  if (proposal.kind === 'issue_update') {
    document.getElementById('action-status').value = proposal.new_status || 'investigating';
    document.getElementById('action-version').value = proposal.expected_version || 1;
    document.getElementById('action-note').value = proposal.note || '';
  } else {
    document.getElementById('action-description').value = proposal.description || '';
  }
  actionKind.dispatchEvent(new Event('change'));
  document.getElementById('write-workflow').scrollIntoView({block:'nearest',behavior:'smooth'});
}
if (actionForm) {
  const resultBox = document.getElementById('action-result');
  const reviewButton = document.getElementById('action-review');
  const confirmButton = document.getElementById('action-confirm');
  const cancelButton = document.getElementById('action-cancel');
  const fields = [actionKind, ...actionForm.querySelectorAll('input,textarea,select')];
  const showActionMessage = text => { resultBox.textContent = text; };
  actionKind.addEventListener('change', () => {
    const issue = actionKind.value === 'issue_update';
    document.getElementById('issue-change-fields').hidden = !issue;
    document.getElementById('next-action-fields').hidden = issue;
    confirmationPanel.hidden = true;
    pendingApprovalId = null;
  });
  function requestPayload() {
    const intent = {kind:actionKind.value,
      issue_id:document.getElementById('action-issue-id').value.trim()};
    if (intent.kind === 'issue_update') {
      intent.new_status = document.getElementById('action-status').value;
      intent.expected_version = Number(document.getElementById('action-version').value);
      intent.note = document.getElementById('action-note').value.trim();
    } else {
      intent.description = document.getElementById('action-description').value.trim();
    }
    return {intent, conversation_id:selectedConversationId};
  }
  actionForm.addEventListener('submit', async event => {
    event.preventDefault(); clearError(); showActionMessage('');
    reviewButton.disabled = true;
    try {
      const response = await fetch('/api/actions/prepare', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify(requestPayload())
      });
      if (!response.ok) throw new Error('Could not prepare action (' + response.status + '). Check issue ID, version and role.');
      const prepared = await response.json();
      pendingApprovalId = prepared.approval_id;
      document.getElementById('action-preview').textContent = JSON.stringify(prepared.intent,null,2);
      confirmationPanel.hidden = false;
      reviewButton.disabled = true;
      fields.forEach(el => { el.disabled = true; });
      showActionMessage('Prepared — no business write has occurred.');
    } catch (error) { showError(error.message); reviewButton.disabled = false; }
  });
  confirmButton.addEventListener('click', async () => {
    if (!pendingApprovalId) return;
    confirmButton.disabled = true;
    try {
      const response = await fetch('/api/actions/' + encodeURIComponent(pendingApprovalId) + '/confirm', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({confirmed:true})
      });
      if (!response.ok) throw new Error('Commit not verified (' + response.status + '). You can retry confirmation safely.');
      const committed = await response.json();
      showActionMessage('Committed and verified. Operation: ' + committed.operation_id +
        '\nReceipt: ' + JSON.stringify(committed.receipt, null, 2));
      confirmationPanel.hidden = true;
      pendingApprovalId = null;
      fields.forEach(el => { el.disabled = false; });
      reviewButton.disabled = false;
    } catch (error) { showError(error.message); }
    finally { confirmButton.disabled = false; }
  });
  cancelButton.addEventListener('click', async () => {
    if (!pendingApprovalId) return;
    try {
      const response = await fetch('/api/actions/' + encodeURIComponent(pendingApprovalId), {
        method:'DELETE', credentials:'same-origin', headers:{'X-CSRF-Token':csrf}
      });
      if (!response.ok) throw new Error('Unable to cancel pending approval');
      pendingApprovalId = null;
      confirmationPanel.hidden = true;
      fields.forEach(el => { el.disabled = false; });
      reviewButton.disabled = false;
      showActionMessage('Action cancelled. No business write occurred.');
    } catch (error) { showError(error.message); }
  });
}


// W11/W12: owner-scoped observability. Untrusted values use textContent only.
const activitySummary = document.getElementById('activity-summary');
const activityRuns = document.getElementById('activity-runs');
const activityDetails = document.getElementById('activity-details');
function smallText(text) { return element('span', String(text), 'activity-meta'); }
function formatDuration(ms) { return ms === null || ms === undefined ? 'In progress' : Number(ms).toLocaleString() + ' ms'; }
async function loadRunDetails(id) {
  if (!activityDetails) return;
  try {
    const response = await fetch('/api/activity/runs/' + encodeURIComponent(id), {credentials:'same-origin'});
    if (!response.ok) throw new Error('Cannot load execution details');
    const run = await response.json();
    activityDetails.hidden = false;
    activityDetails.replaceChildren();
    activityDetails.append(element('strong', 'Execution ' + run.status));
    activityDetails.append(element('p', 'Trace: ' + run.trace_id + ' · ' + formatDuration(run.duration_ms), 'activity-meta'));
    activityDetails.append(element('p', 'Agent: ' + run.role + ' · Blueprint ' + run.blueprint_version, 'activity-meta'));
    const list = element('ol', '', 'activity-tool-list');
    for (const item of run.tool_events || []) {
      const entry = document.createElement('li');
      entry.append(element('strong', item.tool_name));
      entry.append(smallText(' · ' + item.status + ' · ' + formatDuration(item.duration_ms)));
      if (item.evidence_refs && item.evidence_refs.length) {
        entry.append(element('p', 'Evidence: ' + item.evidence_refs.join(', '), 'activity-meta'));
      }
      list.append(entry);
    }
    if (list.children.length) activityDetails.append(list);
    else activityDetails.append(element('p', 'No tools recorded', 'activity-meta'));
  } catch (err) { activityDetails.textContent = err.message; activityDetails.hidden = false; }
}
async function loadActivity() {
  if (!activityRuns) return;
  try {
    const [sumResponse, listResponse, auditResponse] = await Promise.all([
      fetch('/api/activity/summary', {credentials:'same-origin'}),
      fetch('/api/activity/runs?limit=12', {credentials:'same-origin'}),
      fetch('/api/activity/audit?limit=8', {credentials:'same-origin'})
    ]);
    if (sumResponse.status === 401 || listResponse.status === 401 || auditResponse.status === 401) { window.location.href='/login'; return; }
    if (!sumResponse.ok || !listResponse.ok) throw new Error('Agent activity is unavailable');
    const summary = await sumResponse.json();
    const results = await listResponse.json();
    const audit = auditResponse.ok ? await auditResponse.json() : {items:[]};
    const auditContainer = document.getElementById('activity-audit');
    if (auditContainer) {
      auditContainer.replaceChildren();
      for (const event of audit.items) {
        const line = element('div', '', 'activity-audit-entry');
        line.append(element('strong', event.action + ' · ' + event.decision));
        line.append(smallText(' · ' + new Date(event.occurred_at).toLocaleString()));
        auditContainer.append(line);
      }
      if (!audit.items.length) auditContainer.append(element('p', 'No business action events yet.', 'muted'));
    }
    activitySummary.textContent = summary.total_runs + ' runs · ' + summary.completed +
      ' complete · ' + summary.failed + ' failed/interrupted · avg ' + formatDuration(summary.avg_duration_ms);
    activityRuns.replaceChildren();
    for (const run of results.items) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'activity-run';
      b.append(element('strong', run.status + ' · ' + run.role));
      b.append(element('span', new Date(run.started_at).toLocaleString() +
        ' · ' + formatDuration(run.duration_ms) + ' · ' + run.tool_count + ' tools', 'activity-meta'));
      b.addEventListener('click', () => loadRunDetails(run.id));
      activityRuns.append(b);
    }
    if (!results.items.length) activityRuns.append(element('p', 'No executions yet.', 'muted'));
  } catch (err) { activitySummary.textContent = err.message; }
}
const refreshActivity = document.getElementById('activity-refresh');
if (refreshActivity) refreshActivity.addEventListener('click', loadActivity);
loadActivity();
