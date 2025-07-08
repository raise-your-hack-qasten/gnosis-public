const { app, BrowserWindow, Menu } = require("electron");

const createWindow = () => {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
    });

    win.loadURL("http://localhost:3000"); // TODO: Expose env var
};

app.whenReady().then(() => {
    Menu.setApplicationMenu(null);

    createWindow();
});
