from flask import Flask,request,Response

app = Flask(__name__)

@app.route('/')
def main():
	return 'test',200

@app.route('/keep_alive')
def keep_alive():
	return 'Bot is aLive!',200

@app.route('/twitch_eventsub',methods=['POST'])
def twitch_eventsub():
    try:
        if request.method == "POST":
            data = request.json
            challenge = data['challenge']
            print('status:',data['subscription']['status'])

            r = Response(
                response = challenge,
                content_type = 'text/plain',
                status = 200
            )
            return r
        else:
            print("[Warning] Server Received & Refused!")
            return "Refused", 400

    except Exception as e:
        print("[Warning] Error:", e)
        return "Server error", 400
    

def run():
    app.run(host="0.0.0.0", port=11560)

if __name__ == '__main__':
    run()