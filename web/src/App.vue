<template>
  <div v-if="!me" class="authbox">
    <div class="authcard">
      <h2>viki_rag 法律知识库</h2>
      <p class="sub">viki 编译 × RAG 检索 · 每条引用可核对原文</p>
      <input v-model="form.u" placeholder="用户名" @keyup.enter="doAuth(action)"/>
      <input v-model="form.p" type="password" placeholder="密码（至少 6 位）" @keyup.enter="doAuth(action)"/>
      <div class="tabs"><span :class="{on: action==='login'}" @click="action='login'">登录</span><span :class="{on: action==='register'}" @click="action='register'">注册</span></div>
      <button class="big" @click="doAuth(action)">{{ action === 'login' ? '登 录' : '注 册' }}</button>
      <p class="err" v-if="authErr">{{ authErr }}</p>
    </div>
  </div>
  <div v-else class="shell">
    <aside>
      <div class="who">@ {{ me.username }} <em :class="'r'+me.role">{{ me.role === 'admin' ? '管理员' : '用户' }}</em></div>
      <button class="newchat" @click="newChat">＋ 新对话</button>
      <div class="h-title">最近对话（保留 5 条）</div>
      <div v-for="s in sessions" :key="s.id" class="hist" :class="{on: s.id===curId}" @click="openSession(s)">
        <div class="hrow"><div class="h1">{{ s.title }}</div><span class="hdel" title="删除该对话" @click.stop="delSession(s)">✕</span></div><div class="h2">{{ s.saved_at }}</div>
      </div>
      <button v-if="me.role==='admin'" class="matbtn" @click="matTab=true">📚 法律材料录入</button>
      <button class="logout" @click="logout">退出登录</button>
    </aside>
    <section v-if="!matTab">
      <header><h1>法律咨询问答</h1><span class="stats" v-if="stats">{{ stats.articles }} 条文页 · {{ stats.concepts }} 制度页 · 向量 {{ stats.vectors }}</span></header>
      <main ref="mainEl">
        <div v-for="(m,i) in messages" :key="i" class="msg" :class="m.role">
          <div v-if="m.role==='user'" class="bubble">{{ m.text }}</div>
          <template v-else>
            <div class="stages" v-if="m.stages && m.stages.length"><span class="stage" v-for="s in m.stages" :key="s.k">{{ s.k }}<template v-if="s.v"> · {{ s.v }}</template></span></div>
            <div class="bubble"><div class="disclaimer" v-if="m.notice">{{ m.notice }}</div><div v-html="render(m.text)"></div></div>
            <div class="refs" v-if="m.refs && m.refs.length">
              <span v-for="r in m.refs" :key="r.name" class="ref-chip" :class="{bad:r.bad,drop:r.drop}" @click="openPage(r.name)" title="点击核对原文">{{ r.name }}{{ r.drop ? '（已剔除）' : '' }}</span>
            </div>
            <div class="vote" v-if="m.q && m.done">
              <template v-if="m.vote==='up'">这条回答有帮助吗？已记录，谢谢 👍</template>
              <template v-else-if="m.vote==='down'">已记录 👎，会进入人工复核队列</template>
              <template v-else-if="m.showNote">哪里有问题？<input class="note-in" v-model="m.note" placeholder="选填（如：漏了第704条）" @keyup.enter="cast(m,'down',true)"/><span class="vbtn" @click="cast(m,'down',true)">提交复核</span><span class="vbtn dim" @click="cast(m,'down',true)">跳过</span></template>
              <template v-else>这条回答有帮助吗？<span class="vbtn" @click="cast(m,'up')">👍 有用</span><span class="vbtn" @click="cast(m,'down')">👎 有问题</span></template>
            </div>
          </template>
        </div>
      </main>
      <div class="composer"><input v-model="input" :disabled="busy" placeholder="输入法律问题，回车发送" @keyup.enter="send"/><button :disabled="busy||!input.trim()" @click="send">{{ busy?'思考中…':'提问' }}</button></div>
      <div class="note">本内容仅供参考，不构成正式法律意见；重大事项请咨询执业律师。</div>
    </section>
    <section v-else class="material">
      <header><h1>法律材料录入<small>（管理员专属）</small><span class="close" @click="matTab=false">✕ 返回问答</span></h1></header>
      <div class="mform">
        <input v-model="mform.name" placeholder="材料名称，如：最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释"/>
        <input v-model="mform.date" placeholder="生效日期，如 20260101（可留空取今日）"/>
        <textarea v-model="mform.text" rows="16" placeholder="粘贴官方全文文本（markdown 或纯文本）。入库仅代表保存登记；编译仍需人工跑 ingest——本入口不做自动编译。"></textarea>
        <button :disabled="!mform.name||mform.text.length<80||busy" @click="submitMaterial">{{ busy?'提交中…':'录入 sources/' }}</button>
        <p class="err" v-if="mErr">{{ mErr }}</p><p class="okline" v-if="mOk">{{ mOk }}</p>
      </div>
      <div class="mfiles"><b>现有材料</b><div v-for="f in mfiles" :key="f">· {{ f }}</div></div>
    </section>
    <div class="drawer" v-if="page"><span class="close" @click="page=null">✕ 关闭</span><h3>{{ page.path }}</h3><pre>{{ page.content }}</pre></div>
  </div>
</template>
<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
const me=ref(null),form=ref({u:'',p:''}),action=ref('login'),authErr=ref(''),stats=ref(null)
const messages=ref([]),input=ref(''),busy=ref(false),page=ref(null),mainEl=ref(null)
const sessions=ref([]),curId=ref(''),matTab=ref(false),mform=ref({name:'',date:'',text:''}),mErr=ref(''),mOk=ref(''),mfiles=ref([])
let token=localStorage.getItem('vr_tk')||'',ws=null,convId=''
const STAGE={rewrite:'查询改写',nav:'制度导航',recall:'混合召回',rerank:'重排',assemble:'上下文',verify:'引用校验'}
function render(t){return t?marked.parse(t):''}
function headers(){return {'content-type':'application/json','authorization':'Bearer '+token}}
function scroll(){nextTick(()=>{if(mainEl.value)mainEl.value.scrollTop=mainEl.value.scrollHeight})}
async function api(path,body){const opt={headers:headers()};if(body){opt.method='POST';opt.body=JSON.stringify(body)}return (await fetch(path,opt)).json().catch(()=>({error:'网络错误'}))}
async function doAuth(act){
  authErr.value=''
  const r=await api('/api/auth/'+act,{username:form.value.u,password:form.value.p})
  if(r.error){authErr.value=r.error;return}
  if(act==='register'){authErr.value='注册成功，请再点登录';action.value='login';return}
  token=r.token;localStorage.setItem('vr_tk',token);me.value={username:r.username,role:r.role};boot()
}
function logout(){localStorage.removeItem('vr_tk');token='';me.value=null;if(ws)ws.close()}
function connect(){
  if(ws)ws.close()
  ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/ask?token=${token}`)
}
async function delSession(s){
  if(!confirm('删除对话「'+s.title+'」？不可恢复')) return
  await fetch('/api/sessions/'+s.id, {method:'DELETE', headers:headers()})
  if(curId.value===s.id) newChat()
  loadSessions()
}
function newChat(){messages.value=[];curId.value='';convId='';sessionStorage.setItem('vr_cid','')}
async function send(){
  const q=input.value.trim();if(!q||busy.value||!ws||ws.readyState!==1)return
  messages.value.push({role:'user',text:q})
  messages.value.push({role:'bot',text:'',stages:[],refs:[],notice:'',q,done:false,vote:'',showNote:false,note:''})
  const bot=messages.value[messages.value.length-1]
  input.value='';busy.value=true;scroll()
  let raw=''
  const onMsg=(e)=>{const ev=JSON.parse(e.data)
    if(ev.type==='stage'){const label=STAGE[ev.stage]||ev.stage;let v=ev.ms?' '+ev.ms+'ms':''
      if(ev.detail)v+=' '+ev.detail;if(ev.n)v+=' '+ev.n+'条';if(ev.pages)v+=' '+ev.pages.length+'页'
      const s=bot.stages.find(x=>x.k===label);if(s)s.v=v;else bot.stages.push({k:label,v})}
    else if(ev.type==='token'){raw+=ev.text;bot.text=raw;scroll()}
    else if(ev.type==='final'){bot.text=ev.text}
    else if(ev.type==='verify'){bot.refs=[...ev.refs_ok.map(n=>({name:n})),...ev.refs_bad.map(n=>({name:n,bad:true})),...Array.from({length:ev.dropped||0},(_,j)=>({name:'伪引用'+(ev.dropped>1?j+1:''),drop:true}))]}
    else if(ev.type==='done'){bot.done=true;busy.value=false;ws.removeEventListener('message',onMsg);persist()}
    else if(ev.type==='error'){bot.notice='后端错误：'+ev.msg;busy.value=false;ws.removeEventListener('message',onMsg)}}
  ws.addEventListener('message',onMsg)
  const hist = messages.value.filter(m=>m.role==='bot'&&m.done).slice(-5).map(m=>({q:m.q,a:m.text}))
  ws.send(JSON.stringify({text:q, history:hist}))
}
async function persist(){
  if(!curId.value){curId.value=convId||('c'+Date.now().toString(36));}
  const ms=messages.value.filter(m=>m.role==='bot'&&m.done).map(m=>({q:m.q,a:m.text}))
  const r=await api('/api/sessions',{id:curId.value,title:ms[0]?ms[0].q:undefined,messages:ms})
  if(r.ok)loadSessions()
}
async function loadSessions(){sessions.value=await api('/api/sessions');if(!Array.isArray(sessions.value))sessions.value=[]}
function openSession(s){
  curId.value=s.id;convId=s.id
  messages.value=s.messages.flatMap(m=>[{role:'user',text:m.q},{role:'bot',text:m.a,q:m.q,done:true,vote:'',stages:[],refs:[],notice:''}])
}
async function cast(m,v,withNote){
  if(v==='down'&&!withNote&&!m.vote){m.showNote=true;return}
  m.vote=v;m.showNote=false
  api('/api/feedback',{question:m.q,answer:m.text,verdict:v,note:v==='down'?(m.note||''):''})
}
async function openPage(name){const r=await fetch('/api/page?path='+encodeURIComponent('wiki/articles/'+name+'.md'),{headers:headers()});page.value=await r.json()}
async function submitMaterial(){
  mErr.value='';mOk.value='';busy.value=true
  const r=await api('/api/materials',mform.value)
  busy.value=false
  if(r.error){mErr.value=r.error;return}
  mOk.value='已入库：'+r.path+'（编译仍需人工执行 ingest）';mform.value={name:'',date:'',text:''};loadFiles()
}
async function loadFiles(){const r=await api('/api/materials');if(r.files)mfiles.value=r.files}
async function boot(){
  try{stats.value=await (await fetch('/api/stats')).json()}catch(e){}
  connect();loadSessions()
  if(me.value.role==='admin')loadFiles()
}
onMounted(async()=>{
  if(token){const r=await (await fetch('/api/auth/me',{headers:headers()})).json();if(r.username){me.value=r;boot()}else logout()}
})
</script>
