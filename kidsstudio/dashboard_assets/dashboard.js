"use strict";
(() => {
  // Render dynamic labels as text, never HTML. Database notes and titles are untrusted.
  const root = (id) => document.getElementById(id);
  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  };
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };
  const fmt = (val) => new Intl.NumberFormat("ar-IQ").format(val ?? 0);
  let snapshot = null, selected = null;
  const stageNames = {
    complete: "مكتمل ضمن السجل", in_review: "بانتظار مراجعة",
    working: "قيد العمل", pending: "بانتظار التنفيذ",
    not_tracked: "غير مربوط بعد"
  };
  const statusAr = {
    QUEUED: "بالانتظار", LEASED: "قيد التنفيذ",
    COMPLETED: "مهام مكتملة", FAILED: "فشلت", CANCELLED: "ألغيت"
  };
  const selectState = root("state-filter"), selectSeries = root("series-filter");
  const markStatus = (text) => { root("sync-status").textContent = text; };
  function renderMetrics(data) {
    const host = root("metrics"); clear(host);
    const cards = [
      ["الحلقات المخططة", data.overview.episodes_total, "ضمن المنهج", "▤"],
      ["سيناريوهات تنتظر الإنتاج", data.overview.scripts_waiting_production,
        "نصوص معتمدة لم يبدأ تصييرها", "✎"],
      ["فيديوهات بانتظار الجودة", data.overview.episodes_waiting_qa,
        "ليست موافقة للنشر", "◷"],
      ["حلقات معتمدة داخلياً", data.overview.episodes_approved,
        "بعد مراجعة المالك", "✓"]
    ];
    for (const [label, value, tag, icon] of cards) {
      const card=make("article","metric");
      card.append(make("span","icon",icon),make("div","label",label),
                  make("div","number",fmt(value)),make("div","tag",tag));
      host.append(card);
    }
  }
  function renderSeries(data) {
    const host=root("series-list");clear(host);
    const count=root("series-count");
    count.textContent = fmt(data.series.length)+" سلسلة";
    const old=selectSeries.value; clear(selectSeries);
    const def=make("option",null,"كل السلاسل");def.value="";selectSeries.append(def);
    for (const series of data.series) {
      const opt=make("option",null,series.title);opt.value=series.id;
      selectSeries.append(opt);
      const wrap=make("div","series-item");
      const top=make("div","series-top");
      top.append(make("div","series-title",series.title),
                 make("div","series-fraction",fmt(series.approved)+" / "+fmt(series.total)));
      const sub=make("div","series-sub",
          (series.state==="ACTIVE"?"السلسلة النشطة":series.state==="PLANNED"?"مخططة":
           series.state==="PAUSED"?"متوقفة مؤقتاً":"إنتاجها مكتمل داخلياً")
           +" · "+series.language.toUpperCase());
      const prog=make("div","progress");const fill=make("span");
      const ratio=series.total?Math.max(0,Math.min(100,Math.round(series.approved*100/series.total))):0;
      fill.style.width=ratio+"%";prog.append(fill);
      wrap.append(top,sub,prog);host.append(wrap);
    }
    selectSeries.value=Array.from(selectSeries.options).some(o=>o.value===old)?old:"";
    if (!data.series.length) host.append(make("div","empty","ماكو سلاسل مسجلة بعد."));
  }
  function renderQueue(data) {
    const host=root("queue-breakdown");clear(host);
    root("queue-state").textContent=data.queue.paused?"الطابور متوقف":"الطابور فعّال";
    for (const key of ["QUEUED","LEASED","COMPLETED","FAILED","CANCELLED"]) {
      const row=make("div","queue-row");
      row.append(make("span",null,statusAr[key]),make("strong",null,fmt(data.queue.counts[key]??0)));
      host.append(row);
    }
  }
  function ensureStates(data) {
    const old=selectState.value;clear(selectState);
    const all=make("option",null,"كل الحالات");all.value="";selectState.append(all);
    const available=new Map(data.episodes.map(e=>[e.state,e.status_label]));
    for (const [state,label] of available.entries()) {
      const o=make("option",null,label);o.value=state;selectState.append(o);
    }
    selectState.value=Array.from(selectState.options).some(o=>o.value===old)?old:"";
  }
  function showEpisode(episode) {
    const host=root("episode-detail");clear(host);
    if (!episode) {
      host.append(make("p","placeholder","اختَر حلقة من الجدول لعرض مراحلها."));
      return;
    }
    const row=make("div","detail-header");
    row.append(make("h3",null,"الحلقة "+fmt(episode.ordinal)+" — "+episode.title),
               make("span","stagepill "+episode.tone,episode.status_label));
    host.append(row,make("p",null,"الهدف التعليمي: "+episode.objective));
    const list=make("div","timeline");
    for (const stage of episode.stages) {
      const part=make("div","step "+stage.status);
      part.append(make("div","step-name",stage.name),
                  make("div","step-status",stageNames[stage.status]??"غير معروف"));
      list.append(part);
    }
    host.append(list);
    const qa=episode.quality||{state:"NOT_CONFIGURED",criteria_passed:0};
    const states={
      NOT_CONFIGURED:"نظام فحص M7 غير مفعّل",
      NOT_STARTED:"الفحص النهائي لم يبدأ",
      TECH_PASSED_WAITING_HUMAN:"الفحص التقني ناجح · بانتظار المراجعة البشرية",
      CHANGES_REQUESTED:"المراجع طلب تعديلات · لا يمكن اعتماد الحلقة",
      READY_FOR_OWNER_EPISODE_APPROVAL:"المراجعة موثقة · بانتظار اعتماد الحلقة",
      AI_INTERNAL_READY_PRIVATE_ONLY:"مراجعتان AI مستقلتان موثقتان · رفع Private فقط · قرارك بعد الرفع",
      AI_INTERNAL_CHANGES_REQUIRED:"وكلاء المراجعة طلبوا تصحيحات · يمنع رفع الحلقة",
    };
    host.append(make("p","small-explainer",
      "فحص الجودة M7: "+(states[qa.state]||"تحتاج مراجعة فنية")+" · "+
      fmt(qa.criteria_passed||0)+" من 11 معياراً موثقاً"));
    const scenes=episode.scene_progress||{total:0,voice_approved:0,ltx_approved:0,blocked:0};
    if (scenes.total>0) {
      host.append(make("p","small-explainer",
        "المشاهد: "+fmt(scenes.total)+
        " · صوت معتمد "+fmt(scenes.voice_approved)+
        " · تحريك معتمد "+fmt(scenes.ltx_approved)+
        (scenes.blocked ? " · مهام متوقفة "+fmt(scenes.blocked) : "")+
        (scenes.repairs_queued_total ?
          " · إعادة إنتاج محدودة "+fmt(scenes.repairs_queued_total):"")+
        (scenes.repairs_current_pending ?
          " · تصحيحات نشطة "+fmt(scenes.repairs_current_pending):"")));
    }
    const aiScene=episode.ai_scene_reviews||{state:"NOT_STARTED"};
    if (aiScene.state!=="NOT_STARTED") {
      host.append(make("p","small-explainer",
        "مراجعات AI للمشاهد M28: صوت "+fmt(aiScene.voice_ready||0)+
        " · تحريك "+fmt(aiScene.ltx_ready||0)+
        (aiScene.needs_fix ? " · يحتاج تصحيح "+fmt(aiScene.needs_fix) : "")+
        " · تقارير موقّعة، ليست دليلاً على تشغيل نموذج فعلي بذاتها"));
    }
    const orchestration=episode.orchestrator||{state:"NOT_PINNED"};
    const orchestrationArabic={
      NOT_PINNED:"ماكو خطة تشغيل موحدة مثبتة للحلقة",
      PINNED_SOURCE_CURRENT_FILE_NOT_RECHECKED:
        "خطة M32 مسجلة ومصدر السيناريو مطابق؛ يلزم فحص ملف الخطة والأدلة بالأمر المحلي",
      BLOCKED_SCRIPT_CHANGED:"خطة M32 متوقفة: بصمة السيناريو تغيرت"
    };
    host.append(make("p","small-explainer",
      "مدير إنتاج M32: "+
      (orchestrationArabic[orchestration.state]||"تحتاج تدقيقاً")+
      " · اختبار الأجهزة المتكامل غير مؤهل بعد"));
    const continuity=episode.audio_continuity||{state:"NOT_CONFIGURED"};
    const continuityText={
      NOT_CONFIGURED:"فحص الاستمرارية الصوتية غير مفعّل بعد",
      NOT_RECORDED:"لم يُسجّل فحص صوت لمشهد LTX الحالي",
      TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING:
        "تشابه صوتي تقني مسجّل · حركة الشفاه تنتظر فحصك"
    };
    host.append(make("p","small-explainer",
      "استمرارية الصوت M10: "+
      (continuityText[continuity.state]||"تحتاج تحققاً تقنياً جديداً")));
    const priv=episode.private_preview||{state:"NOT_RECORDED"};
    const privStates={
      NOT_RECORDED:"لم تُسجّل نسخة مرفوعة Private بعد",
      PRIVATE_AWAITING_OWNER_REVIEW:"الفيديو الخاص بانتظار قرارك بعد الرفع",
      APPROVED:"المالك قبل النسخة؛ النشر العام يحتاج إجراء مستقل",
      APPROVED_WITH_NOTES:"المالك قبل النسخة مع ملاحظات مستقبلية",
      REVISION_REQUESTED:"المالك طلب تعديلات؛ الفيديو يبقى Private"
    };
    host.append(make("p","small-explainer",
      "مراجعة نسخة YouTube Private: "+(privStates[priv.state]||"غير معروفة")));
    if (priv.url) {
      const link=make("a",null,"فتح النسخة الخاصة للمراجعة");
      link.href=priv.url;link.target="_blank";link.rel="noopener noreferrer";
      host.append(link);
    }
    const note=make("p","small-explainer",
       "ملاحظة: مراحل الصوت والتحريك وتحسين الوجه لا تُعلن كمكتملة بدون سجلات تشغيل موثّقة منفصلة.");
    host.append(note);
  }
  function renderEpisodes(data) {
    const host=root("episodes-body");clear(host);
    const visible=data.episodes.filter(e=>
      (!selectSeries.value||e.series_id===selectSeries.value)&&
      (!selectState.value||e.state===selectState.value));
    for (const episode of visible) {
      const tr=make("tr",selected===episode.series_id+"-"+episode.ordinal?"active":"");
      tr.tabIndex=0;
      const series=data.series.find(s=>s.id===episode.series_id);
      [fmt(episode.ordinal),episode.title,series?.title??episode.series_id].forEach(value=>{
        tr.append(make("td",null,value));
      });
      const status=make("td");
      status.append(make("span","stagepill "+episode.tone,episode.status_label));
      tr.append(status,make("td",null,"v"+fmt(episode.revision)));
      const open=()=>{
        selected=episode.series_id+"-"+episode.ordinal;
        showEpisode(episode);renderEpisodes(data);
      };
      tr.addEventListener("click",open);
      tr.addEventListener("keydown",(e)=>{
        if (e.key==="Enter"||e.key===" ") { e.preventDefault();open(); }
      });
      host.append(tr);
    }
    if (!visible.length) {
      const td=make("td",null,"لا توجد حلقات تطابق الفلاتر.");
      td.colSpan=5;const tr=make("tr");tr.append(td);host.append(tr);
    }
    const chosen=data.episodes.find(e=>selected===e.series_id+"-"+e.ordinal);
    showEpisode(chosen);
  }
  function renderNotes(data) {
    const host=root("notes-list");clear(host);
    for (const note of data.notes) {
      const card=make("div","note");
      const meta=make("div","note-meta");
      const series=data.series.find(s=>s.id===note.series_id);
      meta.append(make("span",null,(series?.title??note.series_id)+
        (note.episode?" · الحلقة "+fmt(note.episode):" · عام")));
      const timestamp=new Date(note.created_at*1000);
      meta.append(make("span",null,Number.isFinite(timestamp.getTime())?
        timestamp.toLocaleDateString("ar-IQ"):"—"));
      card.append(meta,make("div","note-text",note.text));host.append(card);
    }
    if (!data.notes.length)host.append(make("div","empty","ماكو ملاحظات مسجلة حالياً."));
  }
  function renderPrivateReview(data) {
    const info=data.private_previews||{};
    root("private-review-overview").textContent=
      "نسخ تنتظر قرارك: "+fmt(info.pending_review||0)+
      " · طلبات تعديل: "+fmt(info.revision_requests||0)+
      " · مقبولة: "+fmt(info.approved||0)+
      " · مقبولة مع ملاحظات: "+fmt(info.approved_with_notes||0)+
      " · يوتيوب غير متصل مباشرةً؛ هذه حالات مسجلة محلياً فقط.";
  }
  function renderLearning(data) {
    const status=root("learning-status");
    const host=root("learning-findings");clear(host);
    const info=data.learning||{};
    if(info.state!=="OWNER_REVIEWED_ANALYTICS_ONLY") {
      status.textContent="لا يوجد تحليل متصل بعد. نستورد بيانات فعلية موثقة من YouTube Studio قبل أي قرار.";
      return;
    }
    status.textContent="نوافذ القياس المسجلة: "+fmt(info.observed_windows||0)+
      " · اقتراحات للمراجعة: "+fmt(info.proposed||0)+
      " · تجارب مستقبلية اعتمدتها: "+fmt(info.adopted||0);
    const decisions={
      PROPOSED:"مقترح يحتاج موافقة",
      ADOPT_FOR_FUTURE_EXPERIMENT:"معتمد كتجربة لسيناريو مستقبلي",
      REJECT:"مرفوض"
    };
    const descriptions={
      hook_style:"بداية الحلقة",
      story_style:"أسلوب القصة",
      pace_style:"إيقاع المشهد",
      participation_style:"أسلوب مشاركة الطفل"
    };
    for(const item of info.recommendations||[]) {
      const entry=make("div","acceptance-entry");
      entry.append(make("strong",null,
        (descriptions[item.feature]||item.feature)+
        " · "+item.candidate+" مقارنةً بـ "+item.baseline));
      entry.append(make("p",null,
        (decisions[item.state]||item.state)+
        " · السلسلة "+item.series_id+
        " · ارتباط إحصائي لا يثبت سبب التفوق"));
      host.append(entry);
    }
    if(!(info.recommendations||[]).length)
      host.append(make("div","empty",
        "لا توجد نتائج قابلة للمقارنة بعد. نحتاج عدة حلقات منشورة وبيانات احتفاظ ووصول."));
  }
  async function load() {
    markStatus("جاري التحديث...");
    try {
      const res=await fetch("/api/overview",{cache:"no-store"});
      if(!res.ok)throw Error("HTTP "+res.status);
      const data=await res.json();
      if(data.version!==1||!Array.isArray(data.episodes))throw Error("Schema mismatch");
      snapshot=data;
      renderMetrics(data);renderSeries(data);renderQueue(data);
      ensureStates(data);renderEpisodes(data);renderNotes(data);renderLearning(data);
      renderPrivateReview(data);
      const when=new Date(data.generated_at);
      const display=Number.isFinite(when.getTime())?
        when.toLocaleTimeString("ar-IQ"):"—";
      root("last-update").textContent="آخر تحديث: "+display;
      markStatus("البيانات محدثة · "+display);
    } catch (err) {
      markStatus("تعذّر قراءة البيانات المحلية");
    }
  }
  async function checkAcceptance() {
    const status=root("acceptance-status");
    const host=root("acceptance-findings");
    status.textContent="جاري التحقق من البيانات المحلية...";
    clear(host);
    try {
      const response=await fetch("/api/acceptance",{cache:"no-store"});
      if (!response.ok) throw Error("Acceptance HTTP "+response.status);
      const report=await response.json();
      if (!Array.isArray(report.findings) || report.schema_version!==1)
        throw Error("Unsupported acceptance response");
      const descriptions={
        required_schema:"قاعدة البيانات",
        active_series:"السلسلة النشطة",
        episodes:"خطة الحلقات",
        provenance:"ارتباط المهام والبصمات",
        queue_drain:"المهام المنتظرة",
        first_real_episode:"حلقة مكتملة",
        restore_drill:"تجربة استعادة القاعدة",
        private_preview:"المراجعة الخاصة",
        live_chatterbox_ltx:"تأهيل محركات الصوت والتحريك",
        owner_artistic_educational_rights:"الفحص التربوي والفني والحقوق",
        separate_backup:"النسخة الاحتياطية المستقلة"
      };
      const labels={
        PASS:"موثّق",BLOCKED:"مشكلة تحتاج معالجة",
        ACTION:"مطلوب",DEVICE_TEST_REQUIRED:"يتطلب اختبار الماك",
        HUMAN_REVIEW_REQUIRED:"يتطلب مراجعة بشرية"
      };
      status.textContent="نتيجة الفحص: "+report.status+
        " — لا يشمل تشغيل النماذج ولا النشر.";
      for (const entry of report.findings) {
        const wrap=make("div","acceptance-entry");
        const header=make("div","acceptance-top");
        header.append(make("strong",null,descriptions[entry.code]||entry.code),
            make("span","stagepill "+(entry.status==="PASS"?"complete":
                            entry.status==="BLOCKED"?"blocked":"review"),
                 labels[entry.status]||entry.status));
        wrap.append(header,make("p",null,entry.next_action));
        host.append(wrap);
      }
    } catch {
      status.textContent="تعذر فحص الجاهزية. لا تعتمد حالة سابقة من اللوحة.";
    }
  }
  root("acceptance-check").addEventListener("click",checkAcceptance);
  root("refresh-now").addEventListener("click",load);
  selectState.addEventListener("change",()=>snapshot&&renderEpisodes(snapshot));
  selectSeries.addEventListener("change",()=>snapshot&&renderEpisodes(snapshot));
  load();
  setInterval(load,15000);
})();
