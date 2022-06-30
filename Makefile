ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
APP_NAME:=odev

.ONESHELL:

test_build_nc:
	@pushd $(ROOT_DIR) > /dev/null
	@docker build --no-cache --tag $(APP_NAME) .
	@popd > /dev/null

test_build:
	@pushd $(ROOT_DIR) > /dev/null
	@docker build --tag $(APP_NAME) .
	@popd > /dev/null

test_run:
	@pushd $(ROOT_DIR) > /dev/null
	@docker run $(APP_NAME)
	@popd > /dev/null

test: test_build test_run

stop:
	docker stop $(APP_NAME); docker rm $(APP_NAME)
