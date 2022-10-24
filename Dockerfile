FROM python:3.10.5-slim-buster

RUN useradd --user-group --system --create-home --no-log-init userperson
USER userperson
WORKDIR /home/userperson

COPY --chown=userperson:userperson . .

ENV PATH="/home/userperson/.local/bin:$PATH"
ENV VIRTUALENV=./.venv
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN python3 -m venv $VIRTUALENV
RUN . $VIRTUALENV/bin/activate
RUN pip install --user --upgrade pip
RUN pip install --user -r requirements.txt

CMD ["./run_tests.sh"]
