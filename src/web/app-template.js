export default `
<div class="shell">
<aside class="sidebar">
<div class="brand">
<span class="logomark">
<i>
</i>
<i>
</i>
<i>
</i>
</span>
<div>
<strong>冠英</strong>
<small>KOOYING</small>
</div>
</div>
<div class="navlabel">销售工作区</div>
<nav>
<button v-for="n in nav" :class="{selected:page===n.id||(page==='manual'&&n.id==='inbox')}" @click="go(n.id)">
<icon :name="n.icon"/>
<span>{{n.name}}</span>
<em v-if="n.id==='inbox'&&waiting">{{waiting}}</em>
</button>
</nav>
<div class="sidebottom">
<div class="avatar">{{actor.slice(-1)}}</div>
<label>当前销售<select v-model="actor">
<option v-for="x in config.team">{{x}}</option>
</select>
</label>
</div>
</aside>
<main>
<header>
<div class="crumb">
<icon name="globe" :size="15"/> 海外业务 <span>/</span> {{title}}</div>
<span class="service">
<i :class="{bad:!!failed}">
</i>{{failed?'服务异常':'销售工作区'}}</span>
</header>
<div class="content">
<div class="pageheading">
<div>
<div class="date">{{today}}</div>
<h1>{{title}}</h1>
<p>{{subtitle}}</p>
</div>
<button v-if="page==='inbox'" class="ghost refresh" @click="reload(true)" :disabled="refreshing">
<icon name="refresh"/> 刷新</button>
</div>
<div v-if="failed" class="notice" role="alert">{{failed}} <button class="textbtn" @click="reload(true)">重试</button>
</div>
<div v-if="page==='inbox'" class="metrics">
<div v-for="m in metrics" class="metric">
<div class="line">
<span>{{m.name}}</span>
<icon :name="m.icon" :size="17"/>
</div>
<strong>{{m.val}}</strong>
<small>{{m.desc}}</small>
</div>
</div>
<Inbox v-if="page==='inbox'" :rows="rows" :companies="companies" :actor="actor" :config="config" :focus-id="focusId" @focused="focusId=0" @reload="reload" @compose="go('manual')"/>
<Discovery v-else-if="page==='discovery'" :companies="companies" :config="config" @reload="reload"/>
<Companies v-else-if="page==='companies'" :companies="companies" @reload="reload"/>
<Simulator v-else :key="page" :config="config" :manual="page==='manual'" @reload="reload" @open="focus"/>
</div>
</main>
<div class="toast" v-if="notice" role="status">
<icon name="check"/>{{notice}}</div>
</div>
`;
