export default `
<div class="panel">
<div class="panelhead">
<div class="sect">
<icon name="radio"/>
<h2>{{manual?'补录渠道消息':'渠道事件模拟'}}</h2>
</div>
<span class="tag amber">{{manual?'销售录入':'模拟数据'}}</span>
</div>
<form class="formpad" @submit.prevent="submit">
<div class="line">
<h3>消息内容</h3>
<button v-if="!manual" type="button" class="textbtn" @click="example">填入询价样例</button>
</div>
<div class="fields">
<label>消息来源<select v-model="form.channel">
<option v-for="(v,k) in channels" :value="k">{{v}}</option>
</select>
</label>
<label>买家 / 显示名称<input required v-model.trim="form.sender" maxlength="160" placeholder="如 Nadia · 维修厂">
</label>
</div>
<label class="inputlabel">原始消息<textarea v-model="form.body" rows="4" maxlength="8000" placeholder="Can you quote 100 sets of WVA 29289?">
</textarea>
</label>
<label class="inputlabel">附件说明（可选）<input v-model="form.attachment" placeholder="如：旧件背面照片，在原渠道查看">
</label>
<div class="fields">
<label>会话编号<input required v-model.trim="form.thread_key" maxlength="240">
</label>
<label>事件编号<input required v-model.trim="form.event_id" maxlength="220">
</label>
<label>接收时间（本机时区）<input type="datetime-local" required v-model="localTime">
</label>
</div>
<p class="hint">相同事件编号可测试去重；同一渠道、账号和会话下的新事件将追加到原询盘。</p>
<div class="actions">
<button type="button" class="ghost" @click="fresh">新的会话</button>
<button type="button" class="ghost" @click="newEvent">同会话新消息</button>
<button class="primary" :disabled="busy||(!manual&&!config.demo)">{{busy?'处理中…':manual?'保存补录':'发送模拟事件'}}<icon name="arrow"/>
</button>
</div>
</form>
</div>
<div class="panel formpad" v-if="receipt">
<div class="line">
<div>
<small class="micro">接收结果</small>
<h3>{{receipt.duplicate?'重复事件已忽略':'消息已入库'}} · #{{receipt.inquiry_id}}</h3>
</div>
<button class="primary" @click="$emit('open',receipt.inquiry_id)">打开询盘</button>
</div>
</div>

<div v-if="!manual" class="panel">
<div class="panelhead"><h2>渠道接入状态</h2></div>
<div class="cards"><article class="companycard" v-for="r in config.receivers" :key="r.id">
<div class="line"><strong>{{r.name}}</strong><span class="tag">{{r.sync?.error?'接收异常':r.sync?.last_success?'已接收回调':r.configured?'等待回调':'未配置'}}</span></div>
<small>{{r.sync?.error||('最近成功接收：'+stamp(r.sync?.last_success))}}</small></article></div>
</div>
`;
