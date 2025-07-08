const ADD_PAGE_URL = "http://localhost:9000/add_page";
const STORAGE_KEY = "lastPageData";

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

chrome.tabs.onUpdated.addListener(async (tabId, _, tab) => {
  if (!tab.url) return;
  const url = new URL(tab.url);
  await chrome.sidePanel.setOptions({
    tabId,
    path: "sidepanel.html",
    enabled: true,
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PAGE_CONTENT") {
    sendData(message.data);
    initChat(message.data, sender.tab.id, sender.documentId, sender.url);
  } else if (message.type === "GET_LAST_DATA") {
    handleGetLastData(sendResponse);
  } else if (message.type === "RESEND_LAST") {
    handleResendLast(sendResponse);
  }
  return true;
});

chrome.tabs.onRemoved.addListener(function (tabId, removed) {
  console.log("tab removed", tabId, removed);
  chrome.storage.session.getKeys((keys) => {
    keys.forEach((element) => {
      if (element.startsWith(`chat-id-tab-id=${tabId}-`)) {
        chrome.storage.session.remove(element);
      }
    });
  });
});

async function sendData(data) {
  let isSuccess = false;
  try {
    const { ok } = await fetch(ADD_PAGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    isSuccess = ok;
  } catch (error) {
    console.error("Error sending page data:", error);
  }

  chrome.storage.local.set({ [STORAGE_KEY]: { ...data, isSuccess } });
  return isSuccess;
}

function handleGetLastData(sendResponse) {
  chrome.storage.local.get(STORAGE_KEY, (result) => {
    const data = result[STORAGE_KEY];
    if (data) {
      sendResponse({
        title: data.title,
        url: data.url,
        isSuccess: data.isSuccess,
        snippet: data.content.substring(0, 200),
      });
    } else {
      sendResponse({ error: "No data captured yet." });
    }
  });
}

function handleResendLast(sendResponse) {
  chrome.storage.local.get(STORAGE_KEY, async (result) => {
    const data = result[STORAGE_KEY];
    if (!data) {
      console.error(`Cannot resend: key ${STORAGE_KEY} not found`);
      sendResponse({ isSuccess: false });
      return;
    }

    const isSuccess = await sendData(data);
    sendResponse({ isSuccess });
  });
}

INIT_CHAT_PROMPT = `This is not a chat. This conversation will end after you reply, make sure you follow instructions and respect the output format specified in the examples.
Below is text that captures a web page being browsed by the user.
  Accomplish the fololowing tasks:
  1 - Generate a short summary of the contents and bullet points of most interesting bits that user should pay attention to. 
  2 - Using the user's provided memories, determine if the webpage contains content that aligns with the user's memories.
      Only list the facts as available in the memories and the portion of the web page that has a connection to it.
      Some memories might not match, in that case ignore them and do not list them. Only list related memories, if there are any.
      If no memories are related at all, you must return only the exact string: "NO_INTERESTS_FOUND". DO NOT CHANGE THE STRING, ALL IN UPPER CASE.
      Do not explain, summarize, or provide any alternative text if no connection exists. If no mempries were provided, also answer with "NO_INTERESTS_FOUND"
  
  Each task must start with a tag <task1> or <task2>, as shown in following examples:
  Example 1:

  [task1]
  ## Summary
  This webpage ...

  ## Interesting bits
  ...

  [task2]
  - You are interested in chess, one of the recommended articles in the webpage is about chess....

  Example 2:
  [task1]
  Response to task 1

  [task2]
  NO_INTERESTS_FOUND


  Remember that it's either "NO_INTERESTS_FOUND" or memories. Only list relevant memories if there are any.
  Below is the content of the web page:
  #### WEBPAGE ##### \n`;

async function initChat(tabContent, tabId, documentId, url) {
  const user_prompt = "...";
  const modelResponse = await fetch("http://localhost:9000/active_model", {
    method: "GET",
    headers: {
      "Content-type": "application/json",
      Accept: "application/json",
    },
  }).then((response) => {
    return response.json();
  });

  const model = modelResponse.model;
  console.log("model name", model.model);

  console.log("tabContent", tabContent);
  let uploadFile = await fetch(
    "http://localhost:3003/api/v1/files/create_from_payload",
    {
      method: "POST",
      body: JSON.stringify({
        // todo
        content: tabContent.content,
      }),
      headers: {
        "Content-type": "application/json",
        Accept: "application/json",
      },
    }
  ).then((response) => {
    return response.json();
  });

  let uploadFileId = uploadFile.id;
  let uploadFileSize = uploadFile.meta.size;
  let uploadFileName = uploadFile.meta.name;

  const nowTimestamp = Math.floor(Date.now() / 1000);
  const firstMessageUUID = crypto.randomUUID();
  const itemUUID = crypto.randomUUID();
  const newChatRequestBody = JSON.stringify({
    chat: {
      id: "",
      title: "New Chat",
      models: [model],
      params: {},
      messages: [
        {
          id: firstMessageUUID,
          parentId: null,
          childrenIds: [],
          role: "user",
          content: user_prompt,
          files: [
            {
              type: "file",
              file: uploadFile,
              id: uploadFileId,
              url: `/api/v1/files/${uploadFileId}`,
              name: uploadFileName,
              collection_name: `file-${uploadFileId}`,
              status: "uploaded",
              size: uploadFileSize,
              error: "",
              itemId: itemUUID,
            },
          ],
          timestamp: nowTimestamp,
          models: [model],
        },
      ],
      tags: [],
      timestamp: nowTimestamp,
    },
  });

  let newChatResponse = await fetch("http://localhost:3003/api/v1/chats/new", {
    method: "POST",
    body: newChatRequestBody,
    headers: {
      "Content-type": "application/json",
      Accept: "application/json",
    },
  }).then((response) => {
    return response.json();
  });

  let chatId = newChatResponse.id;
  let assistantResponseUUID = crypto.randomUUID();

  console.log("chat_id", chatId);
  chrome.storage.session.set({
    [`chat-id-tab-id=${tabId}-url=${url}`]: chatId,
  });

  // make request to ollama
  let adhocInferenceResponse = await fetch(
    `http://localhost:9000/proxy/chat/completions`,
    {
      method: "POST",
      body: JSON.stringify({
        model: model,
        messages: [
          {
            role: "user",
            content: INIT_CHAT_PROMPT + tabContent.content,
          },
        ],
        stream: false,
      }),
      headers: {
        "Content-Type": "application/json",
      },
    }
  ).then((response) => {
    console.log("re", response);
    return response.json();
  });

  let adhocReply = adhocInferenceResponse.choices[0].message.content;
  console.log("adhoc reply", adhocReply);

  const indextask1 = adhocReply.indexOf("[task1]");
  const indextask2 = adhocReply.indexOf("[task2]");
  const task1Reply = adhocReply.slice(indextask1 + 8, indextask2 - 1);
  const task2Reply = adhocReply.slice(indextask2 + 8, adhocReply.length);
  const containsInterests = !adhocReply.includes("NO_INTERESTS_FOUND");

  let finalReply = "";
  if (containsInterests) {
    finalReply = task2Reply + "\n" + task1Reply;
    // set badge
    chrome.action.setBadgeText({ tabId: tabId, text: "New" });
    chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#ff0f0f" });
    chrome.action.setBadgeTextColor({ tabId: tabId, color: "#ffffff" });
  } else {
    finalReply = task1Reply;
  }
  const completedChaRequest = JSON.stringify({
    chat: {
      models: [model],
      messages: [
        {
          id: firstMessageUUID,
          parentId: null,
          childrenIds: [assistantResponseUUID],
          role: "user",
          content: newChatResponse.chat.messages[0].content,
          files: newChatResponse.chat.messages[0].files,
          timestamp: nowTimestamp,
          models: [model],
        },
        {
          parentId: firstMessageUUID,
          id: assistantResponseUUID,
          childrenIds: [],
          role: "assistant",
          content: finalReply,
          model: model,
          modelName: model,
          modelIdx: 0,
          timestamp: nowTimestamp,
        },
      ],
      params: {},
      files: newChatResponse.chat.messages[0].files,
    },
  });

  let completedChatResponse = await fetch(
    `http://localhost:3003/api/v1/chats/${chatId}`,
    {
      method: "POST",
      body: completedChaRequest,
      headers: {
        "Content-type": "application/json",
        Accept: "application/json",
      },
    }
  ).then((response) => {
    return response.json();
  });

  console.log("Done processing!");
}
