package main

import "fmt"

type TestChild struct {
	value string
}

type TestParent struct {
	Child TestChild
}

func testFunc(value_to_set string, home *string) {
	*home = value_to_set
}

func main() {
	var target TestParent
	fmt.Printf("%+v\n", target)
	var value_to_set string
	value_to_set = "Hello I am a string"
	target.Child.value = value_to_set
	fmt.Printf("%+v\n", target)
	testFunc("This is the new value", &target.Child.value)

	fmt.Printf("%+v\n", target)
}
