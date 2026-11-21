export default `
<div class="panel inbox">
<div class="panelhead">
<div class="sect">
<i class="dot">
</i>
<h2>询盘队列</h2>
<span class="count">{{rows.length}}</span>
</div>
<button class="ghost" @click="$emit('compose')">
<icon name="plus"/> 补录消息</button>
</div>
<div class="toolbar">
<label class="search">
<icon name="search"/>
<input v-model.trim="search" aria-label="搜索询盘" placeholder="搜索买家、消息或负责人">
</label>
<select v-model="channel" aria-label="筛选来源">
<option value="">全部渠道</option>
<option v-for="(v,k) in channels" :value="k">{{v}}</option>
</select>
</div>
<div class="pills">
<button v-for="f in filters" :class="{on:filter===f}" @click="filter=f">{{f}}</button>
</div>
<div class="split">
<div class="ticketlist">
<button class="ticket" v-for="r in visible" :key="r.id" :class="{picked:selected===r.id}" @click="open(r.id)">
<div class="line">
<span class="channel">{{channels[r.channel]}}</span>
<small>#{{String(r.id).padStart(4,'0')}}</small>
</div>
<strong>{{r.buyer}}</strong>
<p>{{r.preview||'附件消息'}}</p>
<div class="line">
<span class="tag" :class="{amber:r.unanswered && r.state!=='已结束'}">{{r.state==='已结束'?'已结束':r.unanswered?'待回复':'已回复'}}</span>
<small>{{r.owner||'待认领'}} · {{age(r.last_in)}}</small>
</div>
</button>
<div class="empty" v-if="!visible.length">没有符合条件的询盘</div>
</div>
<article class="detail" v-if="item">
<div class="line">
<span class="micro">询盘 #{{String(item.id).padStart(4,'0')}}</span>
<span class="tag green">{{item.state}}</span>
</div>
<h2>{{item.buyer}}</h2>
<div class="meta">首次来信 {{stamp(item.created)}} · 北京时间</div>
<div class="fields compact">
<label>负责人<select aria-label="负责人" :value="item.owner" :disabled="busy" @change="edit('owner',$event.target.value)">
<option value="">待认领</option>
<option v-for="x in config.team">{{x}}</option>
</select>
</label>
<label>处理状态<select aria-label="处理状态" :value="item.state" :disabled="busy" @change="edit('state',$event.target.value)">
<option v-for="x in states">{{x}}</option>
</select>
</label>
</div>
<div class="fields compact">
<label>关联企业<select aria-label="关联企业" :value="item.company_id||''" :disabled="busy" @change="edit('company_id',Number($event.target.value)||null)">
<option value="">尚未核实</option>
<option v-for="c in companies" :value="c.id">{{c.name}}</option>
</select>
</label>
<label>采购意图<select aria-label="采购意图" :value="item.intent" :disabled="busy" @change="edit('intent',$event.target.value)">
<option v-for="x in config.intents">{{x}}</option>
</select>
</label>
</div>
<label class="inputlabel">下一步<input :value="item.next_action" maxlength="500" :disabled="busy" @change="edit('next_action',$event.target.value)">
</label>
<div class="tabs">
<button v-for="t in ['消息','处理记录']" @click="tab=t" :class="{active:tab===t}">{{t}} <small>{{t==='消息'?item.messages.length:item.history.length}}</small>
</button>
</div>
<div v-if="tab==='消息'" class="timeline">
<div v-for="m in item.messages" :key="m.id" class="bubble">
<div class="line">
<b>{{channels[m.channel]}}</b>
<small>{{stamp(m.at)}}</small>
</div>
<p class="original">{{m.body}}</p>
<p v-if="m.attachment">附件 · {{m.attachment}}</p>
<p v-if="m.features.translation" class="translation">{{m.features.translation}}</p>
<div class="tags">
<span class="tag">{{m.origin}}</span>
<span class="tag">{{m.features.language}}</span>
<span class="tag" v-if="m.features.role!=='待核实'">{{m.features.role}} · 自述</span>
<span class="tag green" v-for="q in [...m.features.codes,...m.features.quantities]">{{q}}</span>
</div>
</div>
</div>
<div class="timeline" v-else>
<div class="hist" v-for="h in item.history">
<b>{{h.action}}</b>
<small>{{h.actor}} · {{stamp(h.at)}}</small>
<p>{{h.detail}}</p>
</div>
</div>
<label class="inputlabel">跟进记录<textarea v-model="note" rows="2" placeholder="填写备注，或已在原渠道发给客户的回复">
</textarea>
</label>
<div class="actions">
<button class="ghost" :disabled="busy" @click="record('notes')">保存备注</button>
<button class="primary" :disabled="busy" @click="record('reply')">
<icon name="check"/>登记已回复</button>
</div>
<button class="textbtn" @click="showMerge=!showMerge">关联到已有询盘</button>
<div class="merge" v-if="showMerge">
<p>核对买家后将本单消息合入目标询盘，后续消息将跟随目标单。</p>
<select v-model="mergeId">
<option value="">选择目标询盘</option>
<option v-for="r in rows.filter(x=>x.id!==item.id)" :value="r.id">#{{r.id}} {{r.buyer}}</option>
</select>
<button class="ghost" :disabled="!mergeId||busy" @click="mutate('/merge','POST',{target_id:Number(mergeId)},'会话已合并')">确认关联</button>
</div>
</article>
<div v-else class="empty">{{error||(loading?'读取中…':'选择询盘查看消息')}}</div>
</div>
</div>
`;
