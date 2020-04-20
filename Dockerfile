FROM python:3.8-alpine

WORKDIR /app

RUN pip install pipenv

ADD Pipfile /app/
ADD Pipfile.lock /app/

RUN pipenv sync

ADD cryptic_client.py /app/
ADD server.py /app/
ADD cryptic_status.py /app/

CMD pipenv run main
