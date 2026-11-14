const MMMsisToken = artifacts.require("MMMsisToken");

module.exports = async function (deployer) {
  await deployer.deploy(MMMsisToken);
};
