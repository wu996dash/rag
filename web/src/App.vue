<template>
  <header>
    <h1>viki_rag · 法律知识库问答</h1>
    <span class="stats" v-if="stats">{{ stats.articles }} 条文页 · {{ stats.concepts }} 制度页 · {{ stats.cases }} 案例 · 向量 {{ stats.milvus_rows }} 条</span>
  </header>
  <main ref="mainEl">
    <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
      <div v-if="m.role === 'user'" class="bubble">{{ m.text }}</div>
      <template v-else>
        <div class="stages" v-if="m.stages && m.stages.length">
          <span class="stage" v-for="s in m.stages" :key="s.k">{{ s.k }}<template v-if="s.v"> · {{ s.v }}</template></span>
        </div>
        <div class="bubble">
          <div class="disclaimer" v-if="m.notice">{{ m.notice }}</div>
          <div v-html="render(m.text)"></div>
        </div>
        <div class="refs" v-if="m.refs && m.refs.length">
          <span v-for="r in m.refs" :key="r.name" class="ref-chip" :class="{ bad: r.bad, drop: r.drop }" @click="openPage(r.name)" :title="r.bad ? '未通过合法性校验' : (r.drop ? '伪引用已剔除' : '点击核对原文')">
            {{ r.name }}{{ r.drop ? '（已剔除）' : '' }}
          </span>
        </div>
        <div class="vote" v-if="m.q && m.done">
          <template v-if="!m.vote">这条回答有帮助吗？
            <span class="vbtn" @click="cast(m,'up')">👍 有用</span>
            <span class="vbtn" @click="cast(m,'down')">👎 有问题</span>
          </template>
          <template v-else-if="m.vote==='up'">已记录，谢谢 👍</template>
          <template v-else-if="m.showNote">
            <input class="note-in" v-model="m.note" placeholder="哪里不对？（选填，将进入人工复核）" @keyup.enter="cast(m,'down',true)"/>
            <span class="vbtn" @click="cast(m,'down',true)">提交复核</span>
            <span class="vbtn dim" @click="m.vote='down';post(m,'')">跳过</span>
          </template>
          <template v-else>已记录 👎，会进入人工复核队列</template>
        </div>
      </template>
    </div>
  </main>
  <div class="composer">
    <input v-model="input" placeholder="输入法律问题，回车发送（如：竞业限制最长几年？）" @keyup.enter="send" :disabled="busy"/>
    <button @click="send" :disabled="busy || !input.trim()">{{ busy ? '思考中…' : '提问' }}</button>
  </div>
  <div class="note">本内容仅供参考，不构成正式法律意见；重大事项请咨询执业律师。 · viki(LLM Wiki)×RAG · FastAPI+Vue+WebSocket</div>
  <div class="drawer" v-if="page">
    <span class="close" @click="page=null">✕ 关闭</span>
    <h3 style="margin-top:4px">{{ page.path }}</h3>
    <pre>{{ page.content }}</pre>
  </div>
</template>
<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
const messages = ref([]), input = ref(''), busy = ref(false), stats = ref(null), page = ref(null), mainEl = ref(null)
const STAGE = { rewrite: '查询改写', nav: '制度导航', recall: '混合召回', rerank: '重排', assemble: '上下文', verify: '引用校验' }
let ws = null
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/ask`)
  ws.onclose = () => setTimeout(connect, 1500)
}
function render(t) { return t ? marked.parse(t) : '' }
function scroll() { nextTick(() => { if (mainEl.value) mainEl.value.scrollTop = mainEl.value.scrollHeight }) }
function send() {
  const q = input.value.trim()
  if (!q || busy.value || !ws || ws.readyState !== 1) return
  messages.value.push({ role: 'user', text: q })
  messages.value.push({ role: 'bot', text: '', stages: [], refs: [], notice: '', q, done: false, vote: '', showNote: false, note: '' })
  // 必须取数组内的响应式代理对象——直接改 push 前的原始对象不会触发渲染
  const bot = messages.value[messages.value.length - 1]
  input.value = ''; busy.value = true; scroll()
  let raw = ''
  const timer = setTimeout(() => { if (busy.value) { bot.notice = '响应超时，请重试（服务是否已启动？）'; } }, 90000)
  const handler = (ev) => {
    if (ev.type === 'stage') {
      const label = STAGE[ev.stage] || ev.stage
      let v = ''
      if (ev.ms !== undefined && ev.stage !== 'assemble') v = ev.ms + 'ms'
      if (ev.detail) v += ' ' + ev.detail
      if (ev.n) v += ' ' + ev.n + '条'
      if (ev.items && ev.items.length) v += ' ' + ev.items.slice(0, 3).map(x => x.law ? `${x.law}第${x.no}条` : x).join(' ') + (ev.items.length > 3 ? '…' : '')
      if (ev.pages) v += ' ' + ev.pages.length + '页'
      const s = bot.stages.find(x => x.k === label)
      if (s) s.v = v; else bot.stages.push({ k: label, v })
    } else if (ev.type === 'token') { raw += ev.text; bot.text = raw; scroll() }
    else if (ev.type === 'final') { bot.text = ev.text }
    else if (ev.type === 'verify') {
      bot.refs = [
        ...ev.refs_ok.map(n => ({ name: n })),
        ...ev.refs_bad.map(n => ({ name: n, bad: true })),
        ...Array.from({ length: ev.dropped || 0 }, (_, j) => ({ name: '未通过逐字校验的引用' + (ev.dropped > 1 ? j + 1 : ''), drop: true }))
      ]
    } else if (ev.type === 'done') { clearTimeout(timer); busy.value = false; scroll() }
    else if (ev.type === 'error') { clearTimeout(timer); bot.notice = '后端错误：' + ev.msg; busy.value = false }
  }
  const onMsg = (e) => { handler(JSON.parse(e.data)) }
  ws.addEventListener('message', onMsg)
  ws.addEventListener('message', function once(e) { const d = JSON.parse(e.data); if (d.type === 'done' || d.type === 'error') { ws.removeEventListener('message', onMsg); ws.removeEventListener('message', once) } })
  ws.send(JSON.stringify({ text: q }))
}
function post(m, verdict, note) {
  fetch('/api/feedback', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ question: m.q, answer: m.text, verdict, note: note || m.note || '' }) }).catch(() => {})
}
function cast(m, v, withNote) {
  if (v === 'down' && !withNote && !m.vote) { m.showNote = true; return }
  m.vote = v; m.showNote = false
  post(m, v, v === 'down' ? (m.note || '') : '')
}
async function openPage(name) {
  const path = 'wiki/articles/' + name + '.md'
  const r = await fetch('/api/page?path=' + encodeURIComponent(path))
  page.value = await r.json()
}
onMounted(async () => {
  connect()
  try { stats.value = await (await fetch('/api/stats')).json() } catch (e) {}
})
</script>