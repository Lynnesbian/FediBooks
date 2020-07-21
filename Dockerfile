FROM python:3.8.5-slim-buster
WORKDIR /fedibooks
COPY . fedibooks
RUN pip install -r requirements.txt
