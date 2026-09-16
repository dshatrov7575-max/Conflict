(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const COLOR = /^#[0-9a-fA-F]{6}$/;
  const FALLBACK = Object.freeze({HUMAN: "#255cca", AI: "#d05a35"});

  const create = (name, attributes = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      node.setAttribute(key, String(value));
    }
    return node;
  };

  function safeColor(experiment) {
    const raw = experiment?.color;
    return typeof raw === "string" && COLOR.test(raw)
      ? raw.toLowerCase()
      : (FALLBACK[experiment?.kind] || "#596b7c");
  }

  function title(node, text) {
    const item = create("title");
    item.textContent = text;
    node.append(item);
  }

  function absentMarker(svg, point, x, y) {
    const group = create("g", {tabindex: 0, role: "img"});
    const px = x;
    const py = y;
    const state = point.record_state === "NO_RECORD" ? "NO_RECORD" : point.status;
    if (state === "NO_RECORD") {
      group.append(create("circle", {
        cx: px, cy: py, r: 5, fill: "#fff", stroke: "#7b8793",
        "stroke-width": 2, "stroke-dasharray": "2 2",
      }));
    } else if (state === "UNKNOWN") {
      group.append(create("line", {x1: px-5, y1: py-5, x2: px+5, y2: py+5, stroke: "#6e7781", "stroke-width": 2}));
      group.append(create("line", {x1: px+5, y1: py-5, x2: px-5, y2: py+5, stroke: "#6e7781", "stroke-width": 2}));
    } else if (state === "INSUFFICIENT_DATA") {
      group.append(create("polygon", {points: `${px},${py-6} ${px+6},${py+5} ${px-6},${py+5}`, fill: "#fff", stroke: "#9a6a13", "stroke-width": 2}));
    } else if (state === "NOT_APPLICABLE") {
      group.append(create("line", {x1: px-6, y1: py, x2: px+6, y2: py, stroke: "#7b8793", "stroke-width": 3}));
    } else if (state === "OPEN_METHOD") {
      group.append(create("polygon", {points: `${px},${py-6} ${px+6},${py} ${px},${py+6} ${px-6},${py}`, fill: "#fff", stroke: "#744e9b", "stroke-width": 2}));
    } else {
      group.append(create("circle", {cx: px, cy: py, r: 4, fill: "#fff", stroke: "#7b8793", "stroke-width": 2}));
    }
    title(group, `${point.cutoff_date}: ${state || "ABSENT"}`);
    svg.append(group);
  }

  function render(container, series, parameter) {
    container.replaceChildren();
    if (!Array.isArray(series) || !series.length || !parameter) return;

    const slots = series[0].points.map((point) => ({
      id: point.time_slice_id,
      date: point.cutoff_date,
    }));
    for (const item of series) {
      if (!Array.isArray(item.points) || item.points.length !== slots.length) {
        throw new Error("ANALYSIS_SERIES_AXIS_CONFLICT");
      }
      item.points.forEach((point, index) => {
        if (point.time_slice_id !== slots[index].id || point.cutoff_date !== slots[index].date) {
          throw new Error("ANALYSIS_SERIES_AXIS_CONFLICT");
        }
      });
    }

    const width = Math.max(700, container.clientWidth || 700);
    const height = Math.max(190, container.clientHeight || 260);
    const pad = {left: 48, right: 18, top: 18, bottom: 38};
    const svg = create("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `Временной график ${parameter.code}`,
    });
    const min = Number(parameter.scale_min);
    const max = Number(parameter.scale_max);
    if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
      throw new Error("ANALYSIS_PARAMETER_SCALE_INVALID");
    }
    const x = (index) => pad.left + index * (width-pad.left-pad.right) / Math.max(1, slots.length-1);
    const y = (value) => height-pad.bottom-(Number(value)-min)*(height-pad.top-pad.bottom)/(max-min);

    for (let i = 0; i <= 4; i += 1) {
      const value = min + (max-min)*i/4;
      const py = y(value);
      svg.append(create("line", {x1: pad.left, x2: width-pad.right, y1: py, y2: py, stroke: "#e2e8ef"}));
      const label = create("text", {x: 5, y: py+4, fill: "#6d7f91", "font-size": 10});
      label.textContent = value.toFixed(value % 1 ? 1 : 0);
      svg.append(label);
    }
    slots.forEach((slot, index) => {
      if (index % Math.max(1, Math.ceil(slots.length/7)) !== 0 && index !== slots.length-1) return;
      const label = create("text", {x: x(index), y: height-12, fill: "#6d7f91", "font-size": 9, "text-anchor": "middle"});
      label.textContent = slot.date;
      svg.append(label);
    });

    for (const item of series) {
      const color = safeColor(item.experiment);
      let segment = [];
      const flush = () => {
        if (segment.length > 1) {
          svg.append(create("polyline", {
            points: segment.map((point) => `${point[0]},${point[1]}`).join(" "),
            fill: "none", stroke: color, "stroke-width": 2.5,
            "stroke-linejoin": "round", "stroke-linecap": "round",
          }));
        }
        segment = [];
      };
      item.points.forEach((point, index) => {
        if (point.value === null) {
          flush();
          absentMarker(svg, point, x(index), height-pad.bottom-8);
          return;
        }
        const px = x(index);
        const py = y(point.value);
        segment.push([px, py]);
        const circle = create("circle", {
          cx: px, cy: py,
          r: point.status === "DISPUTED" ? 6 : 4.5,
          fill: color,
          stroke: point.status === "DISPUTED" ? "#a05b00" : "#fff",
          "stroke-width": point.status === "DISPUTED" ? 3 : 1.5,
          tabindex: 0,
          role: "img",
        });
        title(circle, `${point.cutoff_date}: ${point.value} · ${point.status} · ${point.confidence_category}`);
        svg.append(circle);
      });
      flush();
    }
    container.append(svg);
  }

  window.AnalysisCharts = Object.freeze({render});
})();
