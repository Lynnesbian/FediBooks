FROM python:3.8.1-slim-buster
WORKDIR /fedibooks
COPY . fedibooks
RUN pip install -r requirements.txt
