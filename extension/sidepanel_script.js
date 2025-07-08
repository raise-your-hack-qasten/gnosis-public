const routine = () => {
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    const key = `chat-id-tab-id=${tab.id}-url=${tab.url}`;

    chrome.storage.onChanged.addListener((changes, namespace) => {
      for (let [changedKey, { oldValue, newValue }] of Object.entries(
        changes
      )) {
        console.log(
          `Storage key "${changedKey}" in namespace "${namespace}" changed.`,
          `Old value was "${oldValue}", new value is "${newValue}".`
        );
        if (namespace == "session" && key == changedKey) {
          document.getElementById("iframe").src =
            document.getElementById("iframe").src;
        }
      }
    });
    // retry hack because sometime it just does not load!
    const updateIframe = () => {
      chrome.storage.session.get(key, (response) => {
        let chatId = response[key];
        let url = `http://localhost:3003/c/${chatId}`;
        if (document.getElementById("iframe").src != url) {
          document.getElementById("iframe").src = url;
        }
        document.getElementById("iframe").style.display = "block";
      });
    };
    updateIframe();
    setInterval(updateIframe, 2000);
  });
};

window.onload = routine;
