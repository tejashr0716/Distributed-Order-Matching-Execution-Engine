CXX = clang++
CXXFLAGS = -O3 -Wall -Wextra -std=c++17 -fPIC -Iinclude
LDFLAGS = 

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SHARED_LIB = liborder_matching.dylib
    SHARED_FLAGS = -dynamiclib
else
    SHARED_LIB = liborder_matching.so
    SHARED_FLAGS = -shared
endif

all: $(SHARED_LIB) benchmark_runner

$(SHARED_LIB): src/order_matching_engine.cpp include/order_matching_engine.h
	$(CXX) $(CXXFLAGS) $(SHARED_FLAGS) src/order_matching_engine.cpp -o $(SHARED_LIB)

benchmark_runner: src/main_benchmark.cpp src/order_matching_engine.cpp include/order_matching_engine.h
	$(CXX) $(CXXFLAGS) src/main_benchmark.cpp src/order_matching_engine.cpp -o benchmark_runner

clean:
	rm -f $(SHARED_LIB) benchmark_runner *.o

.PHONY: all clean
