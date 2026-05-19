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
  head: '<link rel="icon" href="data:,">'
};
