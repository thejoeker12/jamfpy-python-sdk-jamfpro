package main

import (
	"encoding/xml"
)

type test struct {
	TestKey int `xml:"test_key,omitempty"`
}

func main() {
	var test_bool test
	// test_bool.TestKey = 1
	xmlData, _ := xml.MarshalIndent(test_bool, "", "  ")

	println(string(xmlData))
}
