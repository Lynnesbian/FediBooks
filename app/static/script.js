function sendMessage() {
	let id = window.location.href.split("/").slice(-1)[0]
	message = document.getElementById("chatbox-input-box").value
	document.getElementById("chatbox-input-box").value = ''
	document.getElementById("chatbox").innerHTML += `<div class="message-container user"><div class="message user">${message}</div></div>`;
	var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4) {
			if (this.status == 200) {
				message = this.responseText.replace("\n", "<br>");
			} else {
				message = "Encountered an error while trying to get a response.";
			}
			document.getElementById("chatbox").innerHTML += `<div class="message-container bot"><div class="bot-icon"></div><div class="message bot">${this.responseText}</div></div>`;
    }
  };
  xhttp.open("GET", `/bot/chat/${id}/message`, true);
  xhttp.send();
	return false;
}

