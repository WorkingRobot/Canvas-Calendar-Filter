FROM sanicframework/sanic:latest-py3.10

WORKDIR /sanic

COPY . .

RUN pip install -r requirements.txt

EXPOSE 8000

CMD ["python", "server.py"]