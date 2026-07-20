export default {
  title: "Job Market Analyzer",
  root: "src",
  base: "/jobmarket_analyzer/",
  theme: "dashboard",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Geography", path: "/geography"},
    {name: "Work Arrangement", path: "/arrangement"},
    {name: "Skills & Roles", path: "/skills"},
    {name: "Quality & Coverage", path: "/quality"},
    {name: "Methodology & Docs", path: "/methodology"}
  ],
  sidebar: true,
  toc: false,
  footer:
    'Data: Adzuna + public ATS feeds. Source: <a href="https://github.com/alex-wu/jobmarket_analyzer">github.com/alex-wu/jobmarket_analyzer</a>',
  head: `<link rel="icon" href="data:,">
<script>document.addEventListener("click",function(e){
  var a=e.target.closest("a[href]"); if(!a) return;
  if(!a.matches("#observablehq-sidebar a[href], nav a[rel='next'], nav a[rel='prev']")) return;
  var qs=window.location.search; if(!qs) return;
  var h=a.getAttribute("href");
  if(/^(https?:|mailto:|#)/.test(h)) return;
  if(h.indexOf("?")>=0) return;
  e.preventDefault();
  window.location.href=h+qs;
},true);</script>`
};
