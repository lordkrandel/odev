FROM python:3.10.5-slim-buster

RUN useradd --user-group --system --create-home --no-log-init userperson
USER userperson

WORKDIR /home/userperson
ENV VIRTUALENV=./.venv
ENV PATH="/home/userperson/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN python3 -m venv $VIRTUALENV
RUN . $VIRTUALENV/bin/activate

RUN pip install --user --upgrade pip
COPY --chown=userperson:userperson requirements.txt requirements.txt
RUN pip install --user -r requirements.txt

COPY --chown=userperson:userperson . .

CMD ["python3", "./run_tests.py"]
