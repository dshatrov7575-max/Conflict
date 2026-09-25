"use strict";

const form = document.querySelector("#override-form");
if (form) {
  const parameters = new Map(JSON.parse(document.querySelector("#scenario-parameters").textContent)
    .filter(row => row.value !== null).map(row => [row.key, row]));
  const select = form.querySelector("#id_parameter");
  const number = form.querySelector("#id_value");
  const slider = form.querySelector("#scenario-slider");
  const configure = (preserveValue = false) => {
    const parameter = parameters.get(select.value);
    if (!parameter) return;
    for (const input of [number, slider]) {
      input.min = String(parameter.min);
      input.max = String(parameter.max);
    }
    // Never round the decimal field through the coarser slider on load.
    if (!preserveValue) number.value = parameter.value;
    if (number.value !== "" && number.validity.valid) slider.value = number.value;
  };
  select.addEventListener("change", () => configure());
  number.addEventListener("input", () => {
    if (number.value !== "" && number.validity.valid) slider.value = number.value;
  });
  slider.addEventListener("input", () => { number.value = slider.value; });
  configure(number.value !== "");
  form.querySelector("#slider-controls").hidden = false;
}
