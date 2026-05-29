# Container image for both Lambdas (API + collector). yfinance pulls pandas/numpy,
# which are too large for a zip deployment, so we ship an image instead.
# 3.12 is a supported Lambda runtime with prebuilt pandas/yfinance wheels.
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app ${LAMBDA_TASK_ROOT}/app

# Default command = API handler. The collector function overrides this via
# ImageConfig.Command in template.yaml.
CMD ["app.handlers.api_handler"]
