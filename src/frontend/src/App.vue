<script setup>
import { ref,computed,onMounted,onUnmounted } from 'vue'
const items=ref([]), fields=ref({}), sync=ref('连接中'), failure=ref('')
const tab=ref('对话选型'), search=ref(''), selected=ref(''), draft=ref(null), busy=ref(false), revision=ref(null)
const text=ref(''), turns=ref([]), result=ref(null), role=ref('customer'), useModel=ref(true)
const scope=ref('全部规格')
const market=ref('全部市场')
const inquiryMarket=ref('')
const country=ref(''), inquiryCountry=ref('')
const countries={'E':'欧洲','A':'美国','J':'日本','C':'中国','K':'韩国','other':'其他车辆国别','N':'仅无国别'}
function matchesCountry(row,code){return !code || row.country_code===code || row.country_code==='N'}
const quantity=ref(100), unit=ref('套'), timer=ref(null)
async function api(path,data) {
  const response=await fetch('/api/'+path,data?{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Request':'1'},body:JSON.stringify(data)}:{})
  if(response.status===401) throw Error('请先在 5174 销售工作台登录，然后刷新本页。')
  if(!response.ok) throw Error('请求失败 '+response.status)
  return response.json()
}
async function reload() {
  try {
    const r=await api('catalog'); items.value=r.items; fields.value=r.fields; sync.value=r.sync
    if(revision.value && revision.value!==r.revision){result.value=null;draft.value=null}
    revision.value=r.revision
    if(!selected.value) selected.value=r.items.find(x=>x.code==='GYS-067')?.spec_id??r.items[0]?.spec_id
    failure.value=''
  } catch (e) {failure.value=e.message}
}
onMounted(()=>{reload();timer.value=setInterval(async()=>{
  try{const s=await api('status');sync.value=s.sync;if(!busy.value&&revision.value!==s.revision)await reload()}
  catch{sync.value='连接中断'}
},8000)})
onUnmounted(()=>clearInterval(timer.value))
const multiple=computed(()=>{
  const counts=new Map()
  for(const x of items.value){const k=x.code||x.name;if(k)counts.set(k,(counts.get(k)||0)+1)}
  return counts
})
const filtered=computed(()=>items.value.filter(x=>{
  if(market.value!=='全部市场'&&x.market!==market.value)return false
  if(market.value!=='国内' && !matchesCountry(x,country.value))return false
  if(scope.value==='缺冠英编号'&&x.code)return false
  if(scope.value==='同号或同名多记录'&&multiple.value.get(x.code||x.name)<2)return false
  if(scope.value==='照片组待核'&&x.status!=='照片组待核')return false
  return [x.series,x.code,x.name,x.spec_id,x.wva,x.bfmc,x.fmsi,x.brand,x.axle,x.vehicle,x.fit_notes,x.oe_ref,x.catalog_ref,x.reference_raw].some(v=>v?.toLowerCase().includes(search.value.toLowerCase()))
}))
const shown=computed(()=>tab.value==='对话选型'&&result.value?result.value.items:filtered.value)
const current=computed(()=>shown.value.find(r=>r.spec_id===selected.value)||shown.value[0])
const groups=computed(()=>{const g=new Map();for(const r of shown.value){const k=r.series||'系列未知';if(!g.has(k))g.set(k,[]);g.get(k).push(r)}return g})
const detailKeys=['market','section','code','kind','brand','vehicle','axle','position','wva','bfmc','fmsi','oe_ref','catalog_ref','reference_raw','outer_arc','inner_arc','width','thickness','size_raw','holes','taper','arc_value','rivet','kit_ref','lining_ref','fit_notes','comparison','supplier_ref','material','sku']
function choose(id){selected.value=id;draft.value=null}
async function send(example,recheck=false){
  if(busy.value)return
  const msg=(example??text.value).trim();if(!msg&&!recheck)return
  const asked=result.value?.routing?.question
  const context=!recheck && role.value==='customer' && turns.value.at(-1)?.role==='customer' && asked
    ? [...turns.value,{role:'sales',text:asked}] : turns.value
  const next=recheck?turns.value:[...context,{role:role.value,text:msg}]
  if(!next.length)return
  if(next.length>30){failure.value='本次询盘已达 30 条，可新建询盘。';return}
  busy.value=true;failure.value=''
  try{const r=await api('match',{turns:next,use_model:useModel.value,market:inquiryMarket.value||null,country:inquiryMarket.value==='国内'?null:inquiryCountry.value||null});turns.value=next;result.value=r;choose(r.items[0]?.spec_id);if(!recheck)text.value=''}
  catch(e){failure.value=e.message}finally{busy.value=false}
}
function reset(){turns.value=[];result.value=null;text.value='';draft.value=null;inquiryMarket.value='';inquiryCountry.value=''}
async function quoteDraft(){
  if(!current.value||busy.value)return
  busy.value=true;failure.value=''
  try{draft.value=await api('quotes',{spec_id:current.value.spec_id,market:current.value.market||null,quantity:quantity.value,unit:unit.value})}
  catch(e){failure.value=e.message}finally{busy.value=false}
}
function switchTab(t){tab.value=t;draft.value=null;if(t==='产品目录')reload()}
</script>
<template>
<header><b class="logo">G<span>Y</span></b><div><strong>冠英摩擦材料</strong><small>销售选型工作台</small></div><nav><button v-for="t in ['对话选型','产品目录']" :class="{active:tab===t}" @click="switchTab(t)">{{t}}</button></nav><span class="sync" :title="sync">{{sync}}</span></header>
<main><p v-if="failure" class="error" role="alert">{{failure}} <button @click="reload">重新连接</button></p>
<section v-if="tab==='对话选型'" class="inquiry">
<div class="title"><h1>客户询盘</h1><button @click="reset" :disabled="busy">新建询盘</button></div>
<div class="conversation" v-if="turns.length"><p v-for="(m,i) in turns" :key="i"><b>{{m.role==='sales'?'销售':'客户'}}</b>{{m.text}}</p></div>
<form @submit.prevent="send()"><select aria-label="消息来源" v-model="role"><option value="customer">客户</option><option value="sales">销售</option></select><input aria-label="对话内容" v-model="text" placeholder="输入旧件编号、车桥或客户对产品的描述…" maxlength="3000"><button class="primary" :disabled="busy||!text.trim()">{{busy?'处理中…':'分析对话'}}</button></form>
<div class="tools"><label>询盘市场 <select v-model="inquiryMarket" aria-label="询盘市场" :disabled="busy" @change="result=null;draft=null;send(undefined,true)"><option value="">待确认</option><option>国内</option><option>外贸</option></select></label><label v-if="inquiryMarket!=='国内'">车辆国别 <select v-model="inquiryCountry" :disabled="busy" @change="result=null;draft=null;send(undefined,true)"><option value="">全部国别</option><option v-for="(label,code) in countries" :key="code" :value="code">{{label}}</option></select></label><label><input type="checkbox" v-model="useModel"> 使用语言模型提取</label><template v-if="!turns.length"><button @click="send('斯堪尼亚，旧件编号 WVA 19932')">试查 WVA 19932</button><button @click="send('东风 EQ1094 前')">试查 EQ1094 前</button></template></div>
<div class="follow" v-if="result?.routing"><strong>一级索引</strong>
  {{result.routing.prefix || ['market','country','kind'].map(k=>result.routing.slots[k].value || '?').join('')}}
  <small v-if="result.routing.suggested_prefix">语言提示 {{result.routing.suggested_prefix}}，采购市场待确认</small>
  <small>{{result.routing.status==='resolved'?'检索分区':'候选分区'}} {{result.routing.search_prefixes.join('、') || '无'}}</small></div>
<div class="follow" v-if="result"><strong>建议追问</strong> {{result.question}} <small>{{result.mode}} · {{result.count}} 条候选</small></div>
</section>
<div class="workspace">
<aside><div class="title"><h2>{{result&&tab==='对话选型'?'候选规格':'产品目录'}}</h2><span>{{shown.length}}</span></div>
<input v-if="tab==='产品目录'||!result" class="filter" v-model="search" aria-label="筛选目录" placeholder="筛选系列、型号或编码">
<select v-if="tab==='产品目录'" class="filter" v-model="scope" aria-label="资料范围"><option v-for="s in ['全部规格','缺冠英编号','同号或同名多记录','照片组待核']">{{s}}</option></select>
<select v-if="tab==='产品目录'" class="filter" v-model="market" aria-label="目录市场"><option v-for="s in ['全部市场','国内','外贸','待确认']">{{s}}</option></select>
<select v-if="tab==='产品目录' && market!=='国内'" class="filter" v-model="country" aria-label="车辆国别"><option value="">全部国别</option><option v-for="(label,code) in countries" :key="code" :value="code">{{label}}</option></select>
<div class="list"><section v-for="[name,rows] of groups" :key="name"><h3>{{name}} <small>{{rows.length}}</small></h3><button v-for="p in rows" :key="p.spec_id" class="item" :class="{chosen:p.spec_id===current?.spec_id}" @click="choose(p.spec_id)"><b>{{p.code||p.name}}</b><small>{{p.market||'待确认'}} · {{p.code?p.brand||p.kind:p.thickness?'标称厚度 '+p.thickness:p.status}}</small></button></section></div></aside>
<article v-if="current" :key="current.spec_id"><div class="title"><div><span class="tag">{{current.market||'待确认'}} · {{['鼓式','盘式'].includes(current.kind)?current.kind+'刹车片':current.kind}} · {{current.status}}</span><h2 class="part">{{current.code||current.name}}</h2></div><a v-if="current.evidence" :href="current.evidence" target="_blank" rel="noopener">查看目录原页 ↗</a></div>
<p class="muted">{{current.series||'系列未知'}} · 规格键 {{current.spec_id}} <span v-if="current.catalog_country">· {{current.catalog_country}}</span></p>
<div v-if="current.matched" class="signal">匹配线索　{{current.matched.join(' / ')}}<span v-if="current.conflict.length">　冲突　{{current.conflict.map(k=>fields[k]).join('、')}}</span><span v-if="current.missing.length">　待核　{{current.missing.map(k=>fields[k]).join('、')}}</span></div>
<div class="gallery" v-if="current.images.length"><a v-for="im in current.images" :href="im.url" :key="im.url" target="_blank" rel="noopener"><img :src="im.url" loading="lazy" :alt="im.label"><small>{{im.label}}</small></a></div>
<dl><template v-for="k in detailKeys.filter(k=>current[k])" :key="k"><div><dt>{{fields[k]}}</dt><dd>{{current[k]}}</dd></div></template></dl>
<p class="source">资料出处　{{current.source||'未知'}}</p>
<div v-for="s in current.sources" :key="s.crop" class="source">{{s.label}}　<a :href="s.crop" target="_blank" rel="noopener">查看原行 / 规格卡</a>　<a :href="s.page" target="_blank" rel="noopener">整页</a></div>
<div class="quote"><h3>报价草稿</h3><form @submit.prevent="quoteDraft"><label>需求数量 <input type="number" v-model.number="quantity" min="1" max="100000000" required></label><label>单位 <select v-model="unit"><option v-for="u in [...new Set(['套','片','件',current.sale_unit].filter(Boolean))]">{{u}}</option></select></label><button :disabled="busy||current.conflict?.length" class="primary">生成草稿</button></form>
<div v-if="draft&&draft.spec_id===current.spec_id" class="follow"><strong>#{{draft.id}}　{{draft.status}} · {{draft.market}}</strong><p>{{draft.quantity}} {{draft.unit}} · {{draft.total?draft.currency+' '+draft.total:'待补充：'+draft.missing.join('、')}}</p></div></div>
</article><article v-else><h2>暂无匹配记录</h2><p>可补充产品标记、旧件编码或包装照片，再核对目录。</p></article>
</div></main></template>

