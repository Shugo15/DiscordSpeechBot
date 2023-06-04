FROM python:3.11

WORKDIR /bot
COPY requirements.txt /bot/

RUN pip install --upgrade -r requirements.txt && apt-get update && apt-get install -y ffmpeg

COPY . /bot

CMD python -u main.py
