import { initCompare, initEndomapper } from "./viewer.js";

document.getElementById("copy-bib").addEventListener("click", async () => {
  const t = document.getElementById("bibtex").innerText;
  try {
    await navigator.clipboard.writeText(t);
    document.getElementById("copy-bib").textContent = "Copied";
  } catch {
    document.getElementById("copy-bib").textContent = "Select and copy";
  }
});

initCompare();
initEndomapper();
