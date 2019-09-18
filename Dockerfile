FROM python:3.7-slim-buster
WORKDIR /fedibooks
COPY . fedibooks
RUN pip install -r requirements.txt
