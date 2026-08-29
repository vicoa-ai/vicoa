window.debugLogging = (value) => {
  window.parent.postMessage(value, "*");
};
