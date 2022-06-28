ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.ONESHELL:

drebuild:
	@pushd $(ROOT_DIR) > /dev/null
	@docker build --no-cache --tag odev .
	@popd > /dev/null

dbuild:
	@pushd $(ROOT_DIR) > /dev/null
	@docker build --tag odev .
	@popd > /dev/null

drun:
	@pushd $(ROOT_DIR) > /dev/null
	@docker run odev
	@popd > /dev/null
