export default `
<div class="panel">
<div class="panelhead">
<div class="sect">
<icon name="users"/>
<h2>客户档案</h2>
<span class="count">{{companies.length}}</span>
</div>
<button class="primary" @click="start()">
<icon name="plus"/>新建企业</button>
</div>
<div class="toolbar">
<label class="search">
<icon name="search"/>
<input v-model="q" placeholder="搜索名称、地区或业务类型" aria-label="搜索客户">
</label>
<select v-model="role" aria-label="采购能力">
<option value="">全部采购能力</option>
<option v-for="x in purchases">{{x}}</option>
</select>
</div>
<div class="cards">
<article v-for="c in filtered" class="companycard">
<div class="line">
<span class="tag green">{{c.kind}}</span>
<small>{{c.source}}</small>
</div>
<h3>{{c.name}}</h3>
<p>{{c.evidence||'等待补充业务证据'}}</p>
<small v-if="c.contact">公开业务联系 · {{c.contact}}</small>
<div class="tags">
<span class="tag">{{c.country||'地区待核实'}}</span>
<span class="tag amber">{{c.procurement}}</span>
</div>
<div class="line">
<div class="tags">
<a v-if="c.website" :href="safeLink(c.website)" target="_blank" rel="noopener noreferrer">官网 ↗</a>
<a v-if="c.social" :href="safeLink(c.social)" target="_blank" rel="noopener noreferrer">社交主页 ↗</a>
</div>
<a v-if="c.evidence_url" :href="safeLink(c.evidence_url)" target="_blank" rel="noopener noreferrer">业务依据 ↗</a>
<button class="ghost" @click="start(c)">编辑档案</button>
</div>
</article>
</div>
<div class="empty" v-if="!filtered.length">暂无匹配档案，可从买家发现中加入企业。</div>
</div>
<dialog :open="editing" v-if="editing" class="dialogwrap" @keydown.esc="editing=false">
<form class="dialog" @submit.prevent="save">
<div class="line">
<h2>{{id?'编辑客户档案':'新建客户档案'}}</h2>
<button type="button" class="ghost" @click="editing=false">关闭</button>
</div>
<div class="fields">
<label>企业名称<input required v-model="form.name" maxlength="200">
</label>
<label>国家 / 地区<input v-model="form.country">
</label>
<label>业务类型<select v-model="form.kind">
<option v-for="k in kinds">{{k}}</option>
</select>
</label>
<label>采购能力<select aria-label="本企业采购能力" v-model="form.procurement">
<option v-for="k in purchases">{{k}}</option>
</select>
</label>
<label>官方网站<input type="url" v-model="form.website">
</label>
<label>社交主页<input type="url" v-model="form.social">
</label>
</div>
<label class="inputlabel">公开业务联系方式<input v-model="form.contact" maxlength="350" placeholder="公司邮箱、业务电话或视频号名称"></label>
<label class="inputlabel">业务证据<textarea v-model="form.evidence" rows="2">
</textarea>
</label>
<label class="inputlabel">证据链接<input type="url" v-model="form.evidence_url">
</label>
<label class="inputlabel">下一步<input v-model="form.next_action">
</label>
<label class="inputlabel">销售核实记录<textarea rows="2" v-model="form.notes">
</textarea>
</label>
<div class="actions">
<button class="primary" :disabled="busy">保存档案</button>
</div>
</form>
</dialog>
`;
