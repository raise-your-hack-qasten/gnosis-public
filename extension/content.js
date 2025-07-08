function getVisibleText() {
  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode: (node) => {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;

        const style = window.getComputedStyle(parent);
        const isVisible =
          style &&
          style.visibility !== "hidden" &&
          style.display !== "none" &&
          style.opacity !== "0";

        const hasText = node.nodeValue.trim().length > 0;

        return isVisible && hasText
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      },
    }
  );

  let textContent = "";
  while (walker.nextNode()) {
    textContent += walker.currentNode.nodeValue.trim() + "\n\n";
  }

  return textContent.trim();
}

setTimeout(() => {
  const pageData = {
    title: document.title,
    url: window.location.href,
    content: getVisibleText(),
  };

  chrome.runtime.sendMessage({ type: "PAGE_CONTENT", data: pageData });
}, 2000);
