var chatlog = [];

function sendMessage() {
	let id = window.location.href.split("/").slice(-1)[0]
	message = document.getElementById("chatbox-input-box").value
	document.getElementById("chatbox-input-box").value = ''
	document.getElementById("chatbox-input-box").disabled = true;
	chatlog.push(["user", message])
	renderChatlog();
	var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4) {
			if (this.status == 200) {
				message = this.responseText.replace("\n", "<br>");
			} else {
				message = "Encountered an error while trying to get a response.";
			}
			chatlog.push(["bot", message]);
			renderChatlog();
			document.getElementById("chatbox-input-box").disabled = false;

    }
  };
  xhttp.open("GET", `/bot/chat/${id}/message`, true);
	xhttp.send();
	return false;
}

function renderChatlog() {
	let chatbox = document.getElementById("chatbox");
	let out = "";
	if (chatlog.length > 50) {
		chatlog.shift(); //only keep the 50 most recent messages to avoid slowdown
	}
	chatlog.forEach(function(item, i) {
		if (item[0] == "user") {
			out += `<div class="message-container user"><div class="message user">${item[1]}</div></div>`;
		} else {
			out += `<div class="message-container bot"><div class="bot-icon"></div><div class="message bot">${item[1]}</div></div>`;
		}
	})
	chatbox.innerHTML = out;
	chatbox.scrollTop = chatbox.scrollHeight;
}
