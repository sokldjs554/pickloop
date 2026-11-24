(() => {
  function openLinkedReport(hash) {
    const section = document.getElementById(hash.slice(1));
    const panel = section?.querySelector(':scope > details.report-panel');
    if (panel) panel.open = true;
  }
  document.querySelector('.review-nav').addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link) openLinkedReport(link.hash);
  });
  window.addEventListener('hashchange', () => openLinkedReport(location.hash));
  openLinkedReport(location.hash);

  const form = document.getElementById("photo-upload");
  const result = document.getElementById("photo-answer");
  const status = document.getElementById("photo-status");
  const fruit = {apple: "사과", orange: "오렌지", grapefruit: "자몽"};
  const names = {
    "God-Morgon-Apple-Juice": "God Morgon 사과주스",
    "God-Morgon-Orange-Juice": "God Morgon 오렌지주스",
    "God-Morgon-Orange-Red-Grapefruit-Juice": "God Morgon 오렌지·레드자몽 주스",
    Banana: "바나나", Pineapple: "파인애플", Cucumber: "오이",
  };
  const field = (id, value) => { document.getElementById(id).textContent = value; };
  const displayName = (value, fallback) => names[value] || value || fallback;
  async function init() {
    try {
      const response = await fetch("/api/health", {signal: AbortSignal.timeout(4000)});
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return;
      const health = await response.json();
      if (health.photo_recognition !== true) return;
      form.hidden = false;
      document.getElementById("photo-local").hidden = true;
    } catch { /* Static hosting links directly to the local recognizer instructions. */ }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const file = form.elements.image.files[0];
    if (!file) return;
    result.hidden = true;
    if (file.size > 12 * 1024 * 1024) {
      status.textContent = "사진을 12 MiB 이하로 줄여 주세요.";
      return;
    }
    form.elements.run.disabled = true;
    form.elements.image.disabled = true;
    status.textContent = "사진을 읽고 있습니다. 첫 실행에는 모델을 내려받습니다.";
    try {
      const response = await fetch("/api/recognize?require_gtin=true&produce=" + form.elements.produce.checked, {
        method: "POST", headers: {"Content-Type": file.type}, body: file,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "사진을 판별하지 못했습니다.");
      field("photo-name", displayName(data.photo_name, "보류"));
      field("photo-words", (data.printed_fruit_words || []).map(word => fruit[word] || word).join(" · ") || "확인된 단어 없음");
      field("photo-confirmed", displayName(data.confirmed_order_sku, "규격 미확인"));
      field("photo-gtin", (data.order_check_gtins || []).join(" · ") || "읽힌 바코드 없음");
      status.textContent = file.name;
      result.hidden = false;
    } catch (error) {
      status.textContent = String(error.message || error);
    } finally {
      form.elements.image.disabled = false;
      form.elements.run.disabled = false;
    }
  });
  form.elements.image.addEventListener("change", () => {
    result.hidden = true;
    status.textContent = "";
  });
  init();
})();
