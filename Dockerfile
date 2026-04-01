FROM python:3.12

WORKDIR /bridgeipelago

COPY . .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["python", "bridgeipelago.py"]

