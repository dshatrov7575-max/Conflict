(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const create = (name, attributes = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
  };
  function render(container, series, parameter) {
    container.replaceChildren();
    const width = Math.max(700, container.clientWidth || 700), height = Math.max(190, container.clientHeight || 260);
    const pad = {left: 48, right: 18, top: 18, bottom: 38};
    const svg = create("svg", {viewBox: `0 0 ${width} ${height}`, role: "img"});
    const min = Number(parameter.scale_min), max = Number(parameter.scale_max);
    const dates = [...new Set(series.flatMap(item => item.points.map(point => point.cutoff_date)))].sort();
    const x = index => pad.left + index * (width - pad.left - pad.right) / Math.max(1, dates.length - 1);
    const y = value => height - pad.bottom - (Number(value) - min) * (height - pad.top - pad.bottom) / (max - min);
    for (let i = 0; i <= 4; i += 1) {
      const value = min + (max - min) * i / 4, py = y(value);
      svg.append(create("line", {x1: pad.left, x2: width-pad.right, y1: py, y2: py, stroke: "#e2e8ef"}));
      const label = create("text", {x: 5, y: py+4, fill: "#6d7f91", "font-size": 10}); label.textContent = value.toFixed(value % 1 ? 1 : 0); svg.append(label);
    }
    dates.forEach((date, index) => {
      if (index % Math.max(1, Math.ceil(dates.length / 7)) !== 0 && index !== dates.length - 1) return;
      const label = create("text", {x: x(index), y: height-12, fill: "#6d7f91", "font-size": 9, "text-anchor": "middle"}); label.textContent = date; svg.append(label);
    });
    for (const item of series) {
      const color = item.experiment.color || (item.experiment.kind === "HUMAN" ? "#255cca" : "#d05a35");
      const byDate = new Map(item.points.map(point => [point.cutoff_date, point]));
      let segment = [];
      const flush = () => {if (segment.length > 1) svg.append(create("polyline", {points: segment.map(p=>`${p[0]},${p[1]}`).join(" "), fill: "none", stroke: color, "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round"})); segment = [];};
      dates.forEach((date, index) => {
        const point = byDate.get(date);
        if (!point || point.value === null) {
          flush();
          if (point) {
            const px=x(index), py=height-pad.bottom-8;
            svg.append(create("line", {x1:px-5,y1:py-5,x2:px+5,y2:py+5,stroke:"#6e7781","stroke-width":2}));
            svg.append(create("line", {x1:px+5,y1:py-5,x2:px-5,y2:py+5,stroke:"#6e7781","stroke-width":2}));
          }
          return;
        }
        const px=x(index), py=y(point.value); segment.push([px,py]);
        const circle=create("circle", {cx:px,cy:py,r:point.status === "DISPUTED" ? 6 : 4.5,fill:color,stroke:point.status === "DISPUTED" ? "#a05b00" : "#fff","stroke-width":point.status === "DISPUTED" ? 3 : 1.5,tabindex:0});
        const title=create("title"); title.textContent=`${date}: ${point.value} · ${point.status} · ${point.confidence_category}`; circle.append(title); svg.append(circle);
      });
      flush();
    }
    container.append(svg);
  }
  window.AnalysisCharts = Object.freeze({render});
})();
