export default {
  title: "Job Market Analyzer",
  root: "src",
  base: "/jobmarket_analyzer/",
  theme: "dashboard",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Geography", path: "/geography"},
    {name: "Skills & Roles", path: "/skills"},
    {name: "Quality & Coverage", path: "/quality"},
    {name: "Methodology & Docs", path: "/methodology"}
  ],
  sidebar: true,
  toc: false,
  footer:
    'Data: Adzuna + public ATS feeds. Source: <a href="https://github.com/alex-wu/jobmarket_analyzer">github.com/alex-wu/jobmarket_analyzer</a>',
  head: `<link rel="icon" href="data:,">
<script>document.addEventListener("DOMContentLoaded",function(){
  var qs=window.location.search; if(!qs) return;
  var sel="#observablehq-sidebar a[href], nav a[rel='next'], nav a[rel='prev']";
  document.querySelectorAll(sel).forEach(function(a){
    var h=a.getAttribute("href");
    if(/^(https?:|mailto:|#)/.test(h)) return;
    if(h.indexOf("?")>=0) return;
    a.setAttribute("href", h + qs);
  });
});</script>`
};
