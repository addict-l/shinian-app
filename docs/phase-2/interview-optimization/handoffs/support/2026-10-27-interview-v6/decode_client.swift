import Foundation
var states=0
var guides=0
var lives=0
let paths=CommandLine.arguments.dropFirst()
for path in paths {
 let data=try Data(contentsOf:URL(fileURLWithPath:path))
 guard let item=try JSONSerialization.jsonObject(with:data) as? [String:Any], let responses=item["responses"] as? [[String:Any]] else { continue }
 for response in responses {
  states += 1
  if let life=response["life_overview"], !(life is NSNull) {
   _ = try JSONDecoder().decode(LifeOverview.self,from:JSONSerialization.data(withJSONObject:life));lives += 1
  }
  if let session=response["session"] as? [String:Any],let information=session["information"] as? [String:Any],let guided=information["guided_interview"],!(guided is NSNull) {
   _ = try JSONDecoder().decode(GuidedInterviewProgress.self,from:JSONSerialization.data(withJSONObject:guided));guides += 1
  }
 }
}
print("iOS existing Codable models: states=\(states), life=\(lives), guided=\(guides), errors=0")
