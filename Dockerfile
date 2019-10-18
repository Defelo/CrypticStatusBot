FROM python:3.7-alpine

WORKDIR /app

RUN pip install pipenv

ADD Pipfile /app/
ADD Pipfile.lock /app/

RUN pipenv sync

ADD cryptic_status.py /app/
ADD config.json /app/

CMD pipenv run main
