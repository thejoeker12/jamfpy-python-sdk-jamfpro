package main

import "fmt"

// func main() {
// 	// Step 1: Create the inner map
// 	innerMap := make(map[string]string)
// 	innerMap["key"] = "value"
// 	/*
// 		1.
// 			{"string": "string"}
// 	*/

// 	fmt.Println(innerMap)

// 	// Step 2: Create the slice of maps
// 	sliceOfMaps := make([]map[string]string, 0)
// 	/*
// 		2.
// 			[(which can take string:string)]
// 	*/
// 	sliceOfMaps = append(sliceOfMaps, innerMap) // Append the inner map to the slice

// 	/*

// 		Put 1 in 2:
// 			[{"string": "string}]

// 	*/

// 	fmt.Println(sliceOfMaps)

// 	// Step 3: Create the outer map
// 	outerMap := make(map[string][]map[string]string)
// 	/*

// 	 */
// 	outerMap["key"] = sliceOfMaps // Assign the slice of maps to the outer map

// 	// Print the structure
// 	fmt.Println(outerMap)

// 	// Optional: Convert to JSON for clearer visualization
// 	jsonData, err := json.MarshalIndent(outerMap, "", "    ")
// 	if err != nil {
// 		fmt.Println("Error marshalling JSON:", err)
// 		return
// 	}
// 	fmt.Println(string(jsonData))
// }

type test struct {
	TestKey bool `json:"test_key,omitempty"`
}

func main() {
	var test_bool test
	fmt.Println(test_bool.TestKey)
}
