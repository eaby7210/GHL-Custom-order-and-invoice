document.addEventListener("DOMContentLoaded", function () {
  const typeField = document.querySelector("#id_type");
  const valueWrapper = document.querySelector(".form-row.field-value");

  if (!typeField || !valueWrapper) return;

  // helper: replace the value input dynamically
  function updateValueField(type) {
    const valueInput = valueWrapper.querySelector("input, textarea, select");
    if (!valueInput) return;

    // Remove current field content
    while (valueWrapper.firstChild) {
      valueWrapper.removeChild(valueWrapper.firstChild);
    }

    let label = document.createElement("label");
    label.textContent = "Default Value";
    label.setAttribute("for", "id_value");
    valueWrapper.appendChild(label);

    let help = document.createElement("p");
    help.className = "help";
    let input;

    if (type === "radio") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.name = "value";
      input.id = "id_value";
      help.textContent = "Default selected (True/False)";
    } else if (type === "counter") {
      input = document.createElement("input");
      input.type = "number";
      input.name = "value";
      input.id = "id_value";
      input.value = 0;
      help.textContent = "Default counter starting value (integer)";
    } else {
      input = document.createElement("textarea");
      input.name = "value";
      input.id = "id_value";
      help.textContent = "Raw JSON (use for other future field types)";
    }

    valueWrapper.appendChild(input);
    valueWrapper.appendChild(help);
  }

  // listen for changes
  typeField.addEventListener("change", function () {
    updateValueField(this.value);
  });
});
