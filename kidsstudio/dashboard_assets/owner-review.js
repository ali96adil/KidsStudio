"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  const node = (tag, cls, value) => {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (value !== undefined && value !== null) item.textContent = String(value);
    return item;
  };
  const clear = (element) => { while (element.firstChild) element.firstChild.remove(); };
  let ownerToken = "", candidates = [], previews = [];
  const say = (message, bad = false) => {
    const target = el("notice");
    target.textContent = message;
    target.className = bad ? "error" : "";
  };
  async function api(path, data) {
    if (!ownerToken) throw new Error("رمز المالك مطلوب.");
    const headers = { Authorization: "Bearer " + ownerToken };
    const options = { method: data === undefined ? "GET" : "POST", headers, cache: "no-store" };
    if (data !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["X-KidsStudio-Owner-Action"] = "yes";
      options.body = JSON.stringify(data);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      if (response.status === 401) throw new Error("رمز المالك غير صحيح.");
      throw new Error("الطلب مرفوض أو تغيّرت حالة الحلقة. حدّث البيانات وراجع النسخة.");
    }
    return response.json();
  }
  const number = (n) => new Intl.NumberFormat("ar-IQ").format(n);
  const statusText = {
    PRIVATE_AWAITING_OWNER_REVIEW: ["بانتظار قرارك", "pending"],
    APPROVED: ["مقبول · ينتظر إجراء النشر المنفصل", "approved"],
    APPROVED_WITH_NOTES: ["مقبول مع ملاحظات للمستقبل", "approved"],
    REVISION_REQUESTED: ["إرجاع للوكلاء للتعديل · يبقى Private", "changes"]
  };
  const categories = {
    audio: "صوت", animation: "تحريك", text: "نص", education: "فائدة تعليمية",
    timing: "توقيت", visual: "صورة", thumbnail: "صورة مصغرة", other: "عام"
  };
  function parseTimecode(value) {
    const input = value.trim();
    if (!input) return null;
    if (!/^\d{1,2}:\d{2}(?::\d{2})?$/.test(input)) {
      throw new Error("صيغة الوقت: 00:32 أو 01:02:15.");
    }
    const parts = input.split(":").map(Number);
    const seconds = parts.length === 2 ? parts[0] * 60 + parts[1] :
      parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.slice(1).some(x => x > 59) || seconds > 3600) {
      throw new Error("التوقيت يجب أن يكون ضمن ساعة.");
    }
    return seconds;
  }
  const timecode = (secs) => secs === null || secs === undefined ? "" :
    String(Math.floor(secs / 60)).padStart(2,"0") + ":" +
    String(secs % 60).padStart(2,"0");

  async function refresh() {
    const [pending, available] = await Promise.all([
      api("/api/previews"), api("/api/candidates")
    ]);
    previews = pending.previews || [];
    candidates = available.candidates || [];
    el("pending-count").textContent = number(pending.pending_review);
    el("revision-count").textContent = number(pending.revision_requests);
    el("connection").textContent = "متصل · بيانات Studio Brain المحلية";
    const chooser = el("candidate"); clear(chooser);
    const placeholder = node("option", null, "اختَر الحلقة...");
    placeholder.value = ""; chooser.append(placeholder);
    for (const item of candidates) {
      const option = node("option", null,
        item.series_id + " · حلقة " + number(item.episode_number) + " · " + item.title);
      option.value = item.series_id + ":" + item.episode_number;
      chooser.append(option);
    }
    if (!candidates.length) {
      el("register").disabled = true;
    } else {
      el("register").disabled = false;
    }
    renderPreviews();
  }

  async function send(path, body) {
    try {
      await api(path, body);
      say("تم تسجيل القرار أو الملاحظة في سجل الاستوديو.");
      await refresh();
    } catch (err) {
      say(err.message || "تعذّر حفظ الملاحظة.", true);
    }
  }
  function renderPreviews() {
    const host = el("previews"); clear(host);
    if (!previews.length) {
      host.append(node("div","empty","ماكو فيديوهات Private مسجّلة. سجّل أول نسخة بعد رفعها فعلياً."));
      return;
    }
    for (const item of previews) {
      const card = node("article","preview");
      const head = node("div","preview-header");
      const title = node("div");
      title.append(node("h3",null,item.title),
        node("p","meta",item.series_id+" · الحلقة "+number(item.episode_number)+
          " · النسخة "+number(item.version)));
      const state = statusText[item.state] || ["حالة غير معروفة","changes"];
      head.append(title, node("span","status "+state[1],state[0]));
      card.append(head);
      const watch = node("a",null,"فتح الفيديو الخاص على YouTube");
      // Server produces this canonical URL from a checked 11-char video ID.
      watch.href = item.url;
      watch.target = "_blank";
      watch.rel = "noopener noreferrer";
      card.append(watch, node("p","meta",
        "معرّف الفيديو: "+item.video_id+
        (item.platform_privacy_verified ?
        " · تحقق API سابق: Private (لا يضمن حالته الآن)" :
        " · الخصوصية سجلها المالك؛ غير متحقق منها عبر API")));
      const comments = node("div","comment-list");
      for (const comment of item.comments || []) {
        const line = node("div","comment");
        line.append(node("small",null,
          (comment.kind === "DECISION" ? "القرار النهائي" :
           categories[comment.category] || "ملاحظة")+
          (comment.second === null ? "" : " · عند "+timecode(comment.second))));
        line.append(node("span",null,comment.note || "قبول بدون ملاحظات"));
        comments.append(line);
      }
      if (!comments.children.length) comments.append(node("p","hint","لا توجد ملاحظات لهذه النسخة."));
      card.append(comments);
      if (item.state === "PRIVATE_AWAITING_OWNER_REVIEW") {
        const editor = node("div","editor");
        editor.append(node("h4",null,"أضف ملاحظة مرتبطة بوقت أو مكان في الحلقة"));
        const fields = node("div","fields-row");
        const cat = node("select");
        for (const [key,value] of Object.entries(categories)) {
          const opt = node("option",null,value);
          opt.value=key;cat.append(opt);
        }
        const catField = node("div","field");
        catField.append(node("label",null,"نوع الملاحظة"),cat);
        const time = node("input");
        time.placeholder="مثال: 01:24";time.dir="ltr";
        const timeField=node("div","field");
        timeField.append(node("label",null,"التوقيت (اختياري)"),time);
        fields.append(catField,timeField);
        const note = node("textarea");
        note.maxLength=1200;
        note.placeholder="مثال: عند الثانية 42 كلمة الأزرق نطقها غير واضح...";
        const noteField=node("div","field");
        noteField.append(node("label",null,"التفاصيل"),note);
        const save = node("button","secondary","حفظ الملاحظة");
        save.addEventListener("click", async () => {
          try {
            const second=parseTimecode(time.value);
            if (note.value.trim().length<5) throw new Error("اكتب ملاحظة مفيدة.");
            await send("/api/comment",{
              video_id:item.video_id,category:cat.value,
              second,text:note.value.trim()
            });
          } catch (err) { say(err.message,true); }
        });
        const decisionNote = node("textarea");
        decisionNote.maxLength=1200;
        decisionNote.placeholder="ملاحظات ختامية أو تعليمات الوكلاء (مطلوبة إذا قبلت مع ملاحظات أو طلبت تعديلاً)";
        const decisionField = node("div","field");
        decisionField.append(node("label",null,"ملاحظتك عند اتخاذ القرار"),decisionNote);
        editor.append(fields,noteField,save,decisionField);
        const controls = node("div","controls");
        for (const [action,label,cls] of [
          ["APPROVE","قبول النسخة","primary"],
          ["APPROVE_WITH_NOTES","قبول مع ملاحظات","secondary"],
          ["REQUEST_CHANGES","إرجاع للوكلاء للتعديل","danger"]
        ]) {
          const btn=node("button",cls,label);
          btn.addEventListener("click", async () => {
            const text=decisionNote.value.trim();
            if (action!=="APPROVE" && text.length<5) {
              say("اكتب سبباً أو ملاحظات واضحة قبل اتخاذ هذا القرار.",true);
              return;
            }
            const question = action==="REQUEST_CHANGES" ?
              "تأكيد طلب تعديل هذه النسخة؟ تبقى Private ولا تنشر." :
              "تأكيد قرار هذه النسخة؟ القرار محفوظ ولا يُطبّق على النسخ الجديدة.";
            if (!window.confirm(question)) return;
            await send("/api/decision",{video_id:item.video_id,decision:action,note:text});
          });
          controls.append(btn);
        }
        editor.append(controls,node("p","hint",
          "قبول النسخة يسجّل قرارك فقط. تحويلها إلى Public إجراء مستقل لم يتم ربطه بيوتيوب بعد."));
        card.append(editor);
      } else if (item.state==="REVISION_REQUESTED") {
        card.append(node("p","hint",
          "الملاحظات محفوظة لتراجعها الوكلاء. يتطلب الإصلاح تصيير نسخة جديدة، ورفعها Private بمُعرّف جديد، ثم موافقتك عليها."));
      }
      host.append(card);
    }
  }
  el("unlock").addEventListener("click",async()=>{
    ownerToken=el("owner-token").value;
    try {
      await api("/api/health");
      el("owner-token").value="";
      el("login-panel").hidden=true;
      el("workspace").hidden=false;
      say("جلسة مراجعة محلية مفتوحة.");
      await refresh();
    } catch(err) {
      ownerToken="";
      say(err.message||"فشل فتح الجلسة.",true);
    }
  });
  el("lock").addEventListener("click",()=>{
    ownerToken="";candidates=[];previews=[];
    el("workspace").hidden=true;el("login-panel").hidden=false;
    say("تم قفل واجهة المراجعة محلياً.");
  });
  el("refresh").addEventListener("click",()=>refresh().catch(err=>say(err.message,true)));
  el("register").addEventListener("click",async()=>{
    const selected=candidates.find(i=>i.series_id+":"+i.episode_number===el("candidate").value);
    if (!selected) {say("اختَر حلقة معتمدة أولاً.",true);return;}
    const videoId=el("video-id").value.trim();
    if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) {
      say("معرّف YouTube لازم يكون 11 رمزاً.",true);return;
    }
    if (!window.confirm("تأكدت أن الفيديو رُفع فعلياً على YouTube بوضع Private؟"))return;
    await send("/api/private-upload",{
      series_id:selected.series_id,episode_number:selected.episode_number,
      render_job_id:selected.render_job_id,master_sha256:selected.master_sha256,
      video_id:videoId
    });
    el("video-id").value="";
  });
})();
