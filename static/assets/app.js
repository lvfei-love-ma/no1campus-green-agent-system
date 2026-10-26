/* 绿知助手 · 聊天工作区
   纯原生 JavaScript：无框架、无外部依赖（markdown 使用项目内自带的 marked）。
   接口：/api/auth/me、/api/conversations、/api/chat/stream（SSE）。 */

(() => {
  'use strict';

  const state = {
    user: null,
    conversations: [],
    conversationId: null,
    messages: [],
    streaming: false,
    controller: null,
    stickToBottom: true,
    searchTimer: null,
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    sidebar: $('sidebar'),
    overlay: $('overlay'),
    menuBtn: $('menuBtn'),
    sidebarClose: $('sidebarClose'),
    newChatBtn: $('newChatBtn'),
    searchInput: $('searchInput'),
    convList: $('convList'),
    listEmpty: $('listEmpty'),
    accountName: $('accountName'),
    accountMail: $('accountMail'),
    avatar: $('avatar'),
    logoutBtn: $('logoutBtn'),
    convTitle: $('convTitle'),
    clearMemoryBtn: $('clearMemoryBtn'),
    chatScroll: $('chatScroll'),
    welcome: $('welcome'),
    suggestions: $('suggestions'),
    messages: $('messages'),
    typing: $('typing'),
    typingText: $('typingText'),
    composer: $('composer'),
    input: $('input'),
    sendBtn: $('sendBtn'),
    stopBtn: $('stopBtn'),
    toast: $('toast'),
    modal: $('modal'),
    modalTitle: $('modalTitle'),
    modalText: $('modalText'),
    modalConfirm: $('modalConfirm'),
    modalCancel: $('modalCancel'),
  };

  class AuthExpired extends Error {}
  class ApiError extends Error {}

  /* ------------------------------------------------------------ 工具 */
  const escapeHtml = (text) =>
    String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function toast(message, isError = false) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    el.toast.classList.toggle('is-error', isError);
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      el.toast.hidden = true;
    }, isError ? 4200 : 2600);
  }

  function formatDate(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) {
      return `今天 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return '昨天';
    if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1}月${date.getDate()}日`;
    return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
  }

  async function api(path, options = {}) {
    const init = { credentials: 'same-origin', ...options };
    if (init.body && typeof init.body !== 'string') {
      init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
      init.body = JSON.stringify(init.body);
    }
    const res = await fetch(path, init);
    if (res.status === 401) throw new AuthExpired('登录已失效');
    let payload = null;
    try {
      payload = await res.json();
    } catch (err) {
      payload = null;
    }
    if (!res.ok) {
      throw new ApiError((payload && payload.msg) || `请求失败（${res.status}）`);
    }
    return payload;
  }

  function handleAuthExpired() {
    const next = encodeURIComponent(location.pathname + location.search);
    location.replace(`/login?next=${next}`);
  }

  /* ------------------------------------------------------------ 确认框 */
  function confirmDialog({ title, text, confirmLabel = '确定', danger = false }) {
    return new Promise((resolve) => {
      el.modalTitle.textContent = title;
      el.modalText.textContent = text;
      el.modalConfirm.textContent = confirmLabel;
      el.modalConfirm.classList.toggle('is-danger', danger);
      el.modal.hidden = false;
      el.modalConfirm.focus();

      const close = (result) => {
        el.modal.hidden = true;
        el.modalConfirm.removeEventListener('click', onConfirm);
        el.modalCancel.removeEventListener('click', onCancel);
        el.modal.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onKey);
        resolve(result);
      };
      const onConfirm = () => close(true);
      const onCancel = () => close(false);
      const onBackdrop = (event) => {
        if (event.target === el.modal) close(false);
      };
      const onKey = (event) => {
        if (event.key === 'Escape') close(false);
      };
      el.modalConfirm.addEventListener('click', onConfirm);
      el.modalCancel.addEventListener('click', onCancel);
      el.modal.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKey);
    });
  }

  /* ------------------------------------------------------------ Markdown */
  function renderMarkdown(text) {
    if (!window.marked) return escapeHtml(text).replace(/\n/g, '<br>');
    try {
      const html = window.marked.parse(text, { gfm: true, breaks: true });
      const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html');
      const root = doc.body.firstElementChild;
      root.querySelectorAll('script, style, iframe, object, embed').forEach((node) => node.remove());
      root.querySelectorAll('*').forEach((node) => {
        [...node.attributes].forEach((attr) => {
          const name = attr.name.toLowerCase();
          const value = String(attr.value || '').trim().toLowerCase();
          if (name.startsWith('on')) node.removeAttribute(attr.name);
          if ((name === 'href' || name === 'src') && value.startsWith('javascript:')) {
            node.removeAttribute(attr.name);
          }
        });
        if (node.tagName === 'A') {
          node.setAttribute('target', '_blank');
          node.setAttribute('rel', 'noopener noreferrer');
        }
      });
      return root.innerHTML;
    } catch (err) {
      return escapeHtml(text).replace(/\n/g, '<br>');
    }
  }

  /* ------------------------------------------------------------ 侧栏 */
  function openSidebar() {
    el.sidebar.classList.add('open');
    el.overlay.hidden = false;
  }

  function closeSidebar() {
    el.sidebar.classList.remove('open');
    el.overlay.hidden = true;
  }

  function renderConversations() {
    el.convList.querySelectorAll('.conv-item').forEach((node) => node.remove());
    const list = state.conversations;
    el.listEmpty.hidden = list.length > 0;
    if (!list.length) {
      el.listEmpty.textContent = el.searchInput.value.trim()
        ? '没有匹配的对话'
        : '还没有历史对话，先问一个问题吧';
    }
    for (const conv of list) {
      const item = document.createElement('div');
      item.className = 'conv-item' + (conv.id === state.conversationId ? ' active' : '');
      item.dataset.id = conv.id;

      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'conv-open';
      open.setAttribute('aria-label', `打开会话：${conv.title || '空会话'}`);
      const title = document.createElement('span');
      title.className = 'conv-title' + (conv.title ? '' : ' is-empty');
      title.textContent = conv.title || '空会话（未命名）';
      const meta = document.createElement('span');
      meta.className = 'conv-meta';
      meta.textContent = formatDate(conv.updated_at || conv.created_at);
      open.append(title, meta);
      open.addEventListener('click', () => {
        closeSidebar();
        selectConversation(conv.id);
      });

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'conv-del';
      del.setAttribute('aria-label', `删除会话：${conv.title || '空会话'}`);
      del.innerHTML =
        '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg>';
      del.addEventListener('click', (event) => {
        event.stopPropagation();
        deleteConversation(conv);
      });

      item.append(open, del);
      el.convList.appendChild(item);
    }
  }

  async function loadConversations(keyword = '') {
    try {
      const data = await api(`/api/conversations?q=${encodeURIComponent(keyword)}`);
      state.conversations = (data.data && data.data.items) || [];
      renderConversations();
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`会话列表加载失败：${err.message}`, true);
    }
  }

  function updateActiveConversation(conv) {
    const index = state.conversations.findIndex((item) => item.id === conv.id);
    if (index === -1) {
      state.conversations.unshift(conv);
    } else {
      state.conversations[index] = { ...state.conversations[index], ...conv };
      // 会话更新后置顶
      const [item] = state.conversations.splice(index, 1);
      state.conversations.unshift(item);
    }
    renderConversations();
  }

  /* ------------------------------------------------------------ 消息渲染 */
  function setHeader(title) {
    el.convTitle.textContent = title || '新对话';
    document.title = title ? `${title} · 绿知助手` : '绿知助手 · 绿色校园与低碳生活知识问答';
  }

  function showWelcome(show) {
    el.welcome.hidden = !show;
  }

  function stickToBottom() {
    if (state.stickToBottom) {
      el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
    }
  }

  function appendUserMessage(text) {
    const article = document.createElement('article');
    article.className = 'msg user';
    const bubble = document.createElement('div');
    bubble.className = 'msg-user-bubble';
    bubble.textContent = text;
    article.appendChild(bubble);
    el.messages.appendChild(article);
    showWelcome(false);
    stickToBottom();
    return article;
  }

  function appendAssistantMessage(placeholder = '') {
    const article = document.createElement('article');
    article.className = 'msg assistant';
    article.innerHTML = `
      <div class="msg-head">
        <span class="msg-avatar" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 21c5-2.5 8-6.5 8-12V4c-5 0-9 1.5-11 5s-1 8 3 12z"/><path d="M12 21c0-4 1-8 5-11"/>
          </svg>
        </span>
        <span>绿知助手</span>
      </div>
      <div class="msg-body"></div>
      <div class="sources-slot"></div>
      <div class="note-slot"></div>`;
    const body = article.querySelector('.msg-body');
    body.innerHTML = placeholder;
    el.messages.appendChild(article);
    stickToBottom();
    return {
      article,
      body,
      setText(text) {
        body.innerHTML = renderMarkdown(text);
      },
      setHtml(html) {
        body.innerHTML = html;
      },
      setSources(sources) {
        const slot = article.querySelector('.sources-slot');
        slot.innerHTML = '';
        if (!sources || !sources.length) return;
        const details = document.createElement('details');
        details.className = 'sources';
        const summary = document.createElement('summary');
        summary.innerHTML = `参考来源 · ${sources.length} 条
          <svg class="chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>`;
        const list = document.createElement('ol');
        for (const src of sources) {
          const li = document.createElement('li');
          const a = document.createElement('a');
          a.className = 'src-title';
          a.href = src.source_url || '#';
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
          a.textContent = src.title || '未命名资料';
          const meta = document.createElement('span');
          meta.className = 'src-meta';
          const bits = [src.source_name, src.category].filter(Boolean);
          if (src.published_at && src.published_at !== '未注明') bits.push(src.published_at);
          meta.textContent = bits.join(' · ');
          li.append(a, meta);
          list.appendChild(li);
        }
        details.append(summary, list);
        slot.appendChild(details);
      },
      addNote(text, isError = false) {
        const slot = article.querySelector('.note-slot');
        const note = document.createElement('div');
        note.className = isError ? 'msg-error' : 'msg-note';
        note.textContent = text;
        slot.appendChild(note);
      },
      addNoSourceHint() {
        const slot = article.querySelector('.sources-slot');
        if (slot.children.length) return;
        const hint = document.createElement('div');
        hint.className = 'sources-empty';
        hint.textContent = '这次回答没有检索到知识库条目，建议换一种问法。';
        slot.appendChild(hint);
      },
    };
  }

  function renderHistory(messages) {
    el.messages.innerHTML = '';
    if (!messages.length) {
      showWelcome(true);
      return;
    }
    showWelcome(false);
    for (const message of messages) {
      if (message.role === 'user') {
        appendUserMessage(message.content);
        continue;
      }
      const view = appendAssistantMessage();
      view.setText(message.content || '');
      view.setSources(message.sources || []);
      if (message.status === 'interrupted') {
        view.addNote('这条回答没有完整结束（生成被中断或出错），内容可能不完整。');
      }
    }
    state.stickToBottom = true;
    stickToBottom();
  }

  /* ------------------------------------------------------------ 会话操作 */
  async function selectConversation(id) {
    if (state.streaming) {
      toast('正在生成回答，请先停止或等待完成', true);
      return;
    }
    try {
      const data = await api(`/api/conversations/${encodeURIComponent(id)}`);
      state.conversationId = id;
      const conversation = data.data.conversation;
      setHeader(conversation.title);
      renderHistory(data.data.messages || []);
      renderConversations();
      history.replaceState(null, '', `/chat?c=${encodeURIComponent(id)}`);
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`会话加载失败：${err.message}`, true);
    }
  }

  function resetToNew() {
    state.conversationId = null;
    el.messages.innerHTML = '';
    setHeader('');
    showWelcome(true);
    renderConversations();
    history.replaceState(null, '', '/chat');
    el.input.focus();
  }

  async function newConversation() {
    if (state.streaming) {
      toast('正在生成回答，请先停止或等待完成', true);
      return;
    }
    try {
      const data = await api('/api/conversations', { method: 'POST', body: { title: '' } });
      const conv = data.data;
      state.conversations.unshift({ ...conv, message_count: 0 });
      state.conversationId = conv.id;
      el.messages.innerHTML = '';
      setHeader('');
      showWelcome(true);
      renderConversations();
      closeSidebar();
      history.replaceState(null, '', `/chat?c=${encodeURIComponent(conv.id)}`);
      el.input.focus();
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`新建会话失败：${err.message}`, true);
    }
  }

  async function deleteConversation(conv) {
    const ok = await confirmDialog({
      title: '删除这个会话？',
      text: `将删除「${conv.title || '空会话'}」及其全部消息，删除后无法恢复。`,
      confirmLabel: '删除',
      danger: true,
    });
    if (!ok) return;
    if (state.streaming && state.conversationId === conv.id) {
      toast('该会话正在生成回答，请先停止', true);
      return;
    }
    try {
      await api(`/api/conversations/${encodeURIComponent(conv.id)}`, { method: 'DELETE' });
      state.conversations = state.conversations.filter((item) => item.id !== conv.id);
      toast('会话已删除');
      if (state.conversationId === conv.id) {
        state.conversationId = null;
        el.messages.innerHTML = '';
        setHeader('');
        showWelcome(true);
        history.replaceState(null, '', '/chat');
        const next = state.conversations[0];
        if (next) {
          await selectConversation(next.id);
        }
      }
      renderConversations();
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`删除失败：${err.message}`, true);
    }
  }

  async function clearMemory() {
    if (!state.conversationId) {
      toast('当前还没有会话，发送问题后即可清空记忆');
      return;
    }
    const ok = await confirmDialog({
      title: '清空记忆？',
      text: '清空后，接下来提问不会再携带本会话之前的对话内容。\n历史消息仍会保留在左侧会话列表中，不会删除。',
      confirmLabel: '清空记忆',
      danger: false,
    });
    if (!ok) return;
    try {
      const data = await api(`/api/conversations/${encodeURIComponent(state.conversationId)}/memory/clear`, {
        method: 'POST',
      });
      toast(data.msg || '记忆已清空，历史消息仍保留');
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`清空失败：${err.message}`, true);
    }
  }

  async function logout() {
    const ok = await confirmDialog({
      title: '退出登录？',
      text: '退出后需要重新验证身份才能查看历史会话。',
      confirmLabel: '退出',
      danger: false,
    });
    if (!ok) return;
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } catch (err) {
      /* 忽略退出时的网络错误，直接回到登录页 */
    }
    location.replace('/login');
  }

  /* ------------------------------------------------------------ 发送 */
  function setStreaming(streaming) {
    state.streaming = streaming;
    el.sendBtn.disabled = streaming;
    el.sendBtn.hidden = streaming;
    el.stopBtn.hidden = !streaming;
    el.input.disabled = streaming;
    el.clearMemoryBtn.disabled = streaming;
  }

  function autoGrow() {
    el.input.style.height = 'auto';
    el.input.style.height = `${Math.min(el.input.scrollHeight, 168)}px`;
  }

  async function sendQuestion(raw) {
    const query = String(raw || '').trim();
    if (!query || state.streaming) return;

    if (!state.conversationId) {
      try {
        const data = await api('/api/conversations', { method: 'POST', body: { title: '' } });
        state.conversationId = data.data.id;
        state.conversations.unshift({ ...data.data, message_count: 0 });
      } catch (err) {
        if (err instanceof AuthExpired) return handleAuthExpired();
        toast(`创建会话失败：${err.message}`, true);
        return;
      }
    }

    el.input.value = '';
    autoGrow();
    const userNode = appendUserMessage(query);
    const activeConv = state.conversations.find((item) => item.id === state.conversationId);
    if (!activeConv || !activeConv.title) {
      // 服务端会用首条问题生成标题，这里先乐观更新，避免顶部一直显示“新对话”
      setHeader(query.length > 24 ? `${query.slice(0, 23)}…` : query);
    }
    const view = appendAssistantMessage();
    view.body.innerHTML = '<p class="placeholder">正在查找知识库…</p>';
    el.typing.hidden = false;
    el.typingText.textContent = '正在查找知识库…';
    state.stickToBottom = true;
    setStreaming(true);

    const controller = new AbortController();
    state.controller = controller;
    let answer = '';
    let sources = [];
    let doneInfo = null;
    let serverError = '';

    const handleEvent = (eventName, data) => {
      if (eventName === 'meta') {
        if (data.conversation_id && data.conversation_id !== state.conversationId) {
          state.conversationId = data.conversation_id;
        }
        el.typingText.textContent = '正在组织回答…';
        history.replaceState(null, '', `/chat?c=${encodeURIComponent(state.conversationId)}`);
      } else if (eventName === 'answer') {
        answer += data.delta || '';
        el.typing.hidden = true;
        view.setText(answer);
        stickToBottom();
      } else if (eventName === 'sources') {
        sources = sources.concat(data.sources || []);
        view.setSources(sources);
        stickToBottom();
      } else if (eventName === 'done') {
        doneInfo = data;
      } else if (eventName === 'error') {
        serverError = data.message || '服务异常';
      }
    };

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ query, conversation_id: state.conversationId }),
        signal: controller.signal,
      });
      if (res.status === 401) throw new AuthExpired('登录已失效');
      if (!res.ok) {
        let message = `请求失败（${res.status}）`;
        try {
          const payload = await res.json();
          message = payload.msg || message;
        } catch (err) {
          /* ignore */
        }
        throw new ApiError(message);
      }
      if (!res.body) throw new ApiError('当前浏览器不支持流式输出');

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index;
        while ((index = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          let eventName = 'message';
          const dataLines = [];
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
          }
          if (!dataLines.length) continue;
          try {
            handleEvent(eventName, JSON.parse(dataLines.join('\n')));
          } catch (err) {
            /* 单个事件解析失败不影响后续 */
          }
        }
      }
    } catch (err) {
      if (err instanceof AuthExpired) {
        setStreaming(false);
        return handleAuthExpired();
      }
      if (err.name === 'AbortError') {
        if (answer) {
          view.setText(answer);
          view.addNote('已停止生成，已保存的部分回答标记为“未完成”。');
        } else {
          view.addNote('已停止生成，本次没有产生可保存的回答。');
        }
      } else {
        serverError = serverError || err.message || '网络异常';
      }
    } finally {
      el.typing.hidden = true;
      state.controller = null;
      setStreaming(false);
    }

    if (serverError) {
      view.addNote(`回答失败：${serverError}`, true);
      if (!answer) {
        view.body.innerHTML = '';
      }
    } else if (answer) {
      view.setText(answer);
      view.setSources(sources);
      if (doneInfo && doneInfo.status === 'complete' && !sources.length) {
        view.addNoSourceHint();
      }
    } else if (!answer && !serverError) {
      view.addNote('没有收到回答内容，请稍后重试', true);
    }

    // 刷新列表（标题、时间、顺序），并保持当前会话高亮
    await loadConversations(el.searchInput.value.trim());
    const current = state.conversations.find((item) => item.id === state.conversationId);
    if (current) {
      setHeader(current.title);
      updateActiveConversation(current);
    }
    if (userNode) state.stickToBottom = true;
  }

  /* ------------------------------------------------------------ 事件绑定 */
  function bindEvents() {
    el.menuBtn.addEventListener('click', openSidebar);
    el.sidebarClose.addEventListener('click', closeSidebar);
    el.overlay.addEventListener('click', closeSidebar);
    el.newChatBtn.addEventListener('click', newConversation);
    el.clearMemoryBtn.addEventListener('click', clearMemory);
    el.logoutBtn.addEventListener('click', logout);

    el.searchInput.addEventListener('input', () => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => {
        loadConversations(el.searchInput.value.trim());
      }, 250);
    });

    el.composer.addEventListener('submit', (event) => {
      event.preventDefault();
      sendQuestion(el.input.value);
    });

    el.input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!state.streaming) sendQuestion(el.input.value);
      }
    });

    el.input.addEventListener('input', autoGrow);

    el.stopBtn.addEventListener('click', () => {
      if (state.controller) state.controller.abort();
    });

    el.suggestions.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-q]');
      if (!button) return;
      el.input.value = button.dataset.q;
      autoGrow();
      sendQuestion(button.dataset.q);
    });

    el.chatScroll.addEventListener('scroll', () => {
      state.stickToBottom =
        el.chatScroll.scrollHeight - el.chatScroll.scrollTop - el.chatScroll.clientHeight < 90;
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && el.sidebar.classList.contains('open')) closeSidebar();
    });
  }

  /* ------------------------------------------------------------ 启动 */
  async function boot() {
    bindEvents();
    try {
      const data = await api('/api/auth/me');
      state.user = data.data;
    } catch (err) {
      if (err instanceof AuthExpired) return handleAuthExpired();
      toast(`无法连接服务：${err.message}`, true);
      return;
    }

    el.accountName.textContent = state.user.display_name || state.user.email;
    el.accountMail.textContent = state.user.email;
    el.avatar.textContent = (state.user.display_name || '绿').slice(0, 1);

    await loadConversations();

    const params = new URLSearchParams(location.search);
    const current = params.get('c');
    if (current) {
      await selectConversation(current);
    } else if (state.conversations.length) {
      await selectConversation(state.conversations[0].id);
    } else {
      resetToNew();
    }
    autoGrow();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
